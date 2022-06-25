from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Mapping
from functools import partial
import equinox as eqx
import dataclasses
import jax
import jax.numpy as jnp


class Metrics(eqx.Module, ABC):
    """Base class for metrics. A Metrics Object handles calculating intermediate
    metrics from model outputs, accumulating them over batches, then
    calculating final metrics from accumulated metrics. Subclass this class and
    implement the interface for initialisation, accumulation, and finalisation.

    !!! tip
        This class doesn't have to handle 'metrics' in the strictest sense. You could
        implement a `Metrics` class to collect output images for plotting for example.

    !!! example
        Pseudo code for typical `Metrics` usage:

        ```python
        metrics = None
        for batch in dataset:
            batch_metrics = step(batch)  # step returns a Metrics object
            metrics = metrics.merge(batch_metrics) if metrics else batch_metrics

            if time_to_log:
                metrics_dict = metrics.compute()
                #log your metrics here
                metrics = None  # reset the object
        ```
    """

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        """Initialise a metrics object from model output, e.g. preds and targets."""
        raise NotImplementedError

    @abstractmethod
    def merge(self, other: Metrics) -> Metrics:
        """Merge two metrics objects, returning a new object."""
        raise NotImplementedError

    @abstractmethod
    def compute(self) -> Any:
        """Compute final metrics from accumulated metrics."""
        raise NotImplementedError


@partial(jax.jit, static_argnums=2)
def _compute_confusion_matrix(
    preds: jnp.ndarray, labels: jnp.ndarray, num_classes: int = 2
) -> jnp.ndarray:
    """Compute confusion matrix. For internal use in ClassificationMetrics.
    Args:
        preds (jnp.ndarray): 1D array of predictions (not one-hot encoded).
        labels (jnp.ndarray): 1D array of labels (not one-hot encoded).
        num_classes (int, optional): number of classification classes. Defaults to 2.
    Returns:
        jnp.ndarray: Confusion matrix, shape (num_classes, num_classes).
    """
    # magic einsum :)
    return jnp.einsum(
        "nd,ne->de",
        jax.nn.one_hot(labels, num_classes),
        jax.nn.one_hot(preds, num_classes),
    )


@jax.jit
def _compute_metrics_from_cm(confusion_matrix: jnp.ndarray) -> Mapping[str, float]:
    """Compute a battery of metrics from confusion matrix. Reports same metrics as
    `sklearn.metrics.classification_report`. For internal use in ClassificationMetrics.

    Args:
        confusion_matrix (jnp.ndarray): Confusion matrix, shape
            (num_classes, num_classes).

    Returns:
        Mapping[str, float]: Dictionary of metrics.
    """
    all_labels = jnp.einsum("nd->", confusion_matrix)
    condition_positive = jnp.einsum("nd->n", confusion_matrix)
    condition_negative = all_labels - condition_positive
    predicted_positive = jnp.einsum("nd->d", confusion_matrix)
    predicted_negative = all_labels - predicted_positive

    true_positive = jnp.einsum("nn->n", confusion_matrix)
    false_negative = condition_positive - true_positive
    true_negative = predicted_negative - false_negative

    tpr = true_positive / condition_positive
    ppv = true_positive / predicted_positive
    prevalence = condition_positive / (condition_positive + condition_negative)

    # accurcy is "micro averaged", i.e. sum TP and TN over all n classes
    accuracy = jnp.einsum("n->", true_positive + true_negative) / all_labels
    f1 = 2 * (ppv * tpr) / (ppv + tpr)

    num_classes = confusion_matrix.shape[0]

    metrics = {}
    metrics["accuracy"] = accuracy

    metrics["f1_macro"] = jnp.mean(f1)
    metrics["tpr_macro"] = jnp.mean(tpr)
    metrics["ppv_macro"] = jnp.mean(ppv)

    metrics["f1_weighted"] = jnp.sum(f1 * prevalence)
    metrics["tpr_weighted"] = jnp.sum(tpr * prevalence)
    metrics["ppv_weighted"] = jnp.sum(ppv * prevalence)

    for i in range(num_classes):
        metrics[f"f1_class_{i}"] = f1[i]
        metrics[f"tpr_class_{i}"] = tpr[i]
        metrics[f"ppv_class_{i}"] = ppv[i]
        metrics[f"prevalence_class_{i}"] = prevalence[i]
    return metrics


class ClassificationMetrics(Metrics):
    """Basic metrics for multiclass classification tasks.

        Includes: \n
            - Average Loss \n
            - Accuracy \n
            - Prevalence \n
            - F1 score \n
            - Sensitivity (TPR, recall) \n
            - Positive predictive value (PPV, precision)

    Accuracy is reported as Top-1 accuracy which is equal to the micro-average of
    precision/recall/f1. Prevalence is reported on a per-class basis. Precision, Recall
    and F1 are reported three times: per-class, macro-average, and weighted average (by
    prevalence).

    *Not* for multi-label classification.

    !!! info
        See https://en.wikipedia.org/wiki/Confusion_matrix for more on confusion matrices.
        See https://scikit-learn.org/stable/modules/model_evaluation.html for more on
        multiclass micro/macro/weighted averaging.

    """

    _confusion_matrix: jnp.ndarray
    _average_loss: float
    _count: int
    _num_classes: int

    def __init__(
        self, preds: jnp.ndarray, targets: jnp.ndarray, loss: float, num_classes: int
    ) -> None:
        """
        Args:
            preds (jnp.ndarray): Non OH encoded predictions, shape: (batch_size,).
            targets (jnp.ndarray): Non OH encoded targets, shape: (batch_size,).
            loss (float): Average loss over the batch (scalar).
            num_classes (int): Number of classes in classification problem.
        """
        self._confusion_matrix = _compute_confusion_matrix(preds, targets, num_classes)
        self._average_loss = loss
        self._count = preds.shape[0]
        self._num_classes = num_classes

    def merge(self, other: ClassificationMetrics) -> ClassificationMetrics:
        assert isinstance(other, ClassificationMetrics), (
            "Can only merge ClassificationMetrics object with another"
            f" ClassificationMetrics object, got {type(other)=}"
        )
        assert self._num_classes == other._num_classes, (
            "Can only merge metrics with same num_classes, got"
            f" {self._num_classes=} and {other._num_classes=}"
        )
        # can simply sum confusion matrices and count
        new_cm = self._confusion_matrix + other._confusion_matrix
        new_count = self._count + other._count

        # average loss is weighted by count from each object
        new_loss = (
            self._average_loss * self._count + other._average_loss * other._count
        ) / (self._count + other._count)

        return dataclasses.replace(
            self, confusion_matrix=new_cm, average_loss=new_loss, count=new_count
        )

    def compute(self) -> Mapping[str, float]:

        metrics = _compute_metrics_from_cm(self._confusion_matrix)
        metrics["average_loss"] = self._average_loss

        return metrics
