from collections.abc import Callable
from contextlib import AbstractContextManager

type Factory[T] = Callable[[], T]
type ConfigurableFactory[T] = Callable[..., T]
type ContextManagerFactory[T] = Callable[..., AbstractContextManager[T]]
