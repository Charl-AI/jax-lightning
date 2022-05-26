# jax-lightning
Inspired by pytorch-lightning, this is a proof-of-concept library for defining modular and structured models, datasets, training loops, and training stratgies. Built with Equinox.


## Installation

If you want to play with the library or the examples, the supported method for installation is through VSCode devcontainers. Simply run `Remote containers: Clone Repository in Container Volume` from the VScode command palette to clone the repository in an isolated volume, build the image, spin up a container, and mount a vscode window. Alternatively, you can clone the repository normally and run `Remote containers: Open Folder in Container`.

You will need [Docker with the nvidia container runtime installed](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#docker), as well as VScode with the `remote development - containers` extension.

*For the image to build, you will need a GPU+driver capable of running CUDA 11.5 e.g. RTX 3090, you can check this by running nvidia-smi and seeing if 'CUDA Version' is 11.5 or greater*

TODO: create alternate build for CPU only.

### A note on philosophy

*Doesn't this library go against the spirit of using JAX?*

Maybe... I haven't fully made up my mind yet.

If the reason you like JAX is that it gets you away from object-oriented style code and towards a purely functional paradigm, you might not like the inclusion of the OO design patterns in this codebase. Pragmatically though, Python is not a functional language - without a strong, compile-time-checked type system, it can be difficult to reach the functional paradise. Dependency inversion with abstract base classes seems the most Pythonic way to implement interfaces and is hard to avoid if you are trying to write scalable code. Importantly, not everyone who uses JAX is a functional programming evangelist. Some people simply want to use a familiar framework with a well though out set of user-facing abstractions - they might not care about the details of how pure functions make JAX beautiful (although I do).

As I said. I am undecided as to whether this is a great idea. This is highly experimental. It's inevitable that someone is going to come along and try to force JAX back into an OO mould, so it might as well be me :p.
