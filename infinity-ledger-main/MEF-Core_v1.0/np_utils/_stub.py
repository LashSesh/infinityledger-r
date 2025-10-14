"""A minimal NumPy compatibility layer for the MEF-Core tests.

This module provides just enough functionality of the NumPy API for the
unit tests and the simplified core implementation to run without the real
NumPy dependency.  It implements small array containers with the
operations that are exercised inside the repository and lightweight
implementations of ``numpy.linalg`` and ``numpy.random`` helpers.  The goal
is determinism and readability rather than raw performance.

The implementation favours Python lists under the hood – the custom
``SimpleArray`` class derives from ``list`` and overloads arithmetic
operators so that it behaves similarly to ``numpy.ndarray`` for the small
dimensional vectors that are used throughout the project.
"""

from __future__ import annotations

import cmath
import math
import random as _random
import statistics
import builtins
from datetime import datetime, timedelta
from typing import Any, Iterable, Iterator, List, Sequence, Tuple, Union
from contextlib import contextmanager

import hashlib as _hashlib

builtins.datetime = datetime
builtins.timedelta = timedelta
builtins.hashlib = _hashlib

Number = Union[int, float]


def _to_float(value: Union[Number, str]) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise TypeError(f"Cannot convert {value!r} to float") from exc


class SimpleArray(list):
    """Tiny ``ndarray`` replacement for one dimensional data."""

    def __init__(self, values: Iterable[Union[Number, complex, Sequence]]):
        super().__init__(values)

    def __getitem__(self, item):  # type: ignore[override]
        if isinstance(item, tuple):
            if len(item) != 2:
                raise TypeError("Only 2D indexing supported in stub")
            row, col = item
            return super().__getitem__(row)[col]
        return super().__getitem__(item)

    def __setitem__(self, key, value):  # type: ignore[override]
        if isinstance(key, tuple):
            if len(key) != 2:
                raise TypeError("Only 2D assignment supported in stub")
            row, col = key
            row_ref = super().__getitem__(row)
            if isinstance(col, slice):
                if isinstance(value, (int, float)):
                    seq = [float(value)] * len(row_ref[col])
                else:
                    seq = list(value)
                row_ref[col] = seq
            else:
                row_ref[col] = value
            return
        if isinstance(key, (list, SimpleArray)):
            if isinstance(value, (int, float)):
                for idx in key:
                    super().__setitem__(idx, float(value))
            else:
                for idx, val in zip(key, value):
                    super().__setitem__(idx, val)
            return
        super().__setitem__(key, value)

    # ------------------------------------------------------------------
    # Helpers
    def _binary_op(self, other, op):
        if isinstance(other, (int, float, complex)):
            return SimpleArray(op(x, other) for x in self)
        if isinstance(other, (list, SimpleArray, tuple)):
            if len(other) != len(self):
                raise ValueError("operands have different lengths")
            return SimpleArray(op(x, y) for x, y in zip(self, other))
        return NotImplemented

    def _unary_op(self, op):
        return SimpleArray(op(x) for x in self)

    # ------------------------------------------------------------------
    # Arithmetic operations
    def __add__(self, other):
        return self._binary_op(other, lambda a, b: a + b)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        return self._binary_op(other, lambda a, b: a - b)

    def __rsub__(self, other):
        if isinstance(other, (int, float, complex)):
            return SimpleArray(other - x for x in self)
        if isinstance(other, (list, SimpleArray, tuple)):
            if len(other) != len(self):
                raise ValueError("operands have different lengths")
            return SimpleArray(x - y for x, y in zip(other, self))
        return NotImplemented

    def __mul__(self, other):
        return self._binary_op(other, lambda a, b: a * b)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        return self._binary_op(other, lambda a, b: a / b)

    def __neg__(self):
        return self._unary_op(lambda x: -x)

    def __matmul__(self, other):
        if not isinstance(other, (list, SimpleArray, tuple)):
            return NotImplemented
        if not self or not isinstance(self[0], (list, SimpleArray, tuple)):
            raise TypeError("left operand must be a matrix")
        matrix = [list(row) for row in self]
        vector = [float(x) for x in _flatten(other)]
        result = []
        for row in matrix:
            row_vals = [float(x) for x in _flatten(row)]
            result.append(sum(r * v for r, v in zip(row_vals, vector)))
        return SimpleArray(result)

    # ------------------------------------------------------------------
    def copy(self) -> "SimpleArray":
        return SimpleArray(self)

    def tolist(self) -> List:
        return list(self)

    def __getitem__(self, item):
        if isinstance(item, (list, tuple, SimpleArray)):
            return SimpleArray(list.__getitem__(self, int(i)) for i in item)
        return list.__getitem__(self, item)

    def __pow__(self, power):
        if isinstance(power, (int, float)):
            return SimpleArray((float(x) ** power) for x in self)
        return NotImplemented

    def tobytes(self) -> bytes:
        return b"".join(float(x).hex().encode("ascii") for x in self)

    def sum(self) -> float:
        return float(__builtins__["sum"](float(x) for x in self))


def _ensure_array(values: Union[Sequence, SimpleArray]) -> SimpleArray:
    if isinstance(values, SimpleArray):
        return values
    if isinstance(values, (list, tuple)):
        return SimpleArray(values)
    raise TypeError(f"Unsupported type for array conversion: {type(values)!r}")


def array(values: Union[Sequence, SimpleArray]) -> SimpleArray:
    if isinstance(values, SimpleArray):
        return values.copy()
    if isinstance(values, (list, tuple)):
        converted = []
        for item in values:
            if isinstance(item, (list, tuple, SimpleArray)):
                converted.append(array(item))
            elif isinstance(item, (int, float, complex)):
                converted.append(float(item))
            else:
                converted.append(item)
        return SimpleArray(converted)
    raise TypeError(f"Cannot create array from {values!r}")


def asarray(values: Union[Sequence, SimpleArray], dtype: Union[str, type, None] = None):
    base = array(values)

    def _cast(val):
        if isinstance(val, SimpleArray):
            return SimpleArray(_cast(v) for v in val)
        return float(val)

    if dtype in (float, None):
        return _cast(base)
    return base


def zeros(
    length: Union[int, Tuple[int, ...]],
    dtype: Union[str, type, None] = None,
    *,
    like: Any | None = None,
) -> SimpleArray:
    return _filled_array(length, 0.0)


def ones(
    length: Union[int, Tuple[int, ...]],
    dtype: Union[str, type, None] = None,
    *,
    like: Any | None = None,
) -> SimpleArray:
    return _filled_array(length, 1.0)


def full(
    length: Union[int, Tuple[int, ...]],
    fill_value: Number,
    dtype: Union[str, type, None] = None,
    *,
    like: Any | None = None,
) -> SimpleArray:
    return _filled_array(length, float(fill_value))


def _filled_array(length: Union[int, Tuple[int, ...]], value: float) -> SimpleArray:
    if isinstance(length, int):
        return SimpleArray(value for _ in range(length))
    if len(length) == 1:
        return SimpleArray(value for _ in range(length[0]))
    return SimpleArray(_filled_array(length[1:], value) for _ in range(length[0]))


def _infer_shape(values: Any) -> Tuple[int, ...]:
    if isinstance(values, (SimpleArray, list, tuple)):
        if not values:
            return (0,)
        sub_shape = _infer_shape(values[0])
        return (len(values),) + sub_shape
    return ()


def zeros_like(values: Any) -> Any:
    shape = _infer_shape(values)
    if not shape:
        return 0.0
    if len(shape) == 1:
        return _filled_array(shape[0], 0.0)
    return _filled_array(shape, 0.0)


def arange(stop: int) -> SimpleArray:
    return SimpleArray(range(stop))


def diff(values: Sequence[Number]) -> SimpleArray:
    values = list(float(v) for v in values)
    return SimpleArray(values[i + 1] - values[i] for i in range(len(values) - 1))


def concatenate(arrays: Sequence[Sequence[Number]]) -> SimpleArray:
    result: List[float] = []
    for arr in arrays:
        result.extend(float(x) for x in arr)
    return SimpleArray(result)


def stack(arrays: Sequence[Sequence[Number]]) -> SimpleArray:
    return SimpleArray(array(arr) for arr in arrays)


def roll(sequence: Sequence, shift: int) -> SimpleArray:
    data = list(sequence)
    if not data:
        return SimpleArray([])
    shift %= len(data)
    return SimpleArray(data[-shift:] + data[:-shift]) if shift else SimpleArray(data)


def diag(values: Sequence[Number]) -> SimpleArray:
    values = list(values)
    size = len(values)
    matrix: List[List[float]] = []
    for i in range(size):
        row = [0.0] * size
        row[i] = float(values[i])
        matrix.append(row)
    return SimpleArray(SimpleArray(row) for row in matrix)


def eye(n: int, m: int | None = None, dtype: Union[str, type, None] = None) -> SimpleArray:
    if m is None:
        m = n
    matrix: List[List[float]] = []
    for i in range(n):
        row = [0.0] * m
        if i < m:
            row[i] = 1.0
        matrix.append(row)
    return SimpleArray(SimpleArray(row) for row in matrix)


def dot(a: Sequence[Number], b: Sequence[Number]) -> float:
    return float(sum(float(x) * float(y) for x, y in zip(a, b)))


def sum(values: Sequence[Number]) -> float:  # type: ignore[override]
    return float(__builtins__["sum"](float(x) for x in values))


def prod(values: Sequence[Number]) -> float:
    result = 1.0
    for value in values:
        result *= float(value)
    return float(result)


def mean(values: Sequence[Number], axis: int | None = None) -> Union[float, SimpleArray]:
    if axis is None:
        data = list(float(x) for x in _flatten(values))
        if not data:
            return 0.0
        return float(statistics.fmean(data))
    if axis != 0:
        raise NotImplementedError("only axis=0 is supported in this stub")
    columns = list(zip(*values))
    return SimpleArray(statistics.fmean(float(x) for x in column) for column in columns)


def std(values: Sequence[Number], axis: int | None = None) -> Union[float, SimpleArray]:
    if axis is None:
        return float(statistics.pstdev(float(x) for x in _flatten(values)))
    if axis != 0:
        raise NotImplementedError("only axis=0 is supported in this stub")
    columns = list(zip(*values))
    return SimpleArray(statistics.pstdev(float(x) for x in column) for column in columns)


def var(values: Sequence[Number], axis: int | None = None) -> Union[float, SimpleArray]:
    if axis is None:
        return float(statistics.pvariance(float(x) for x in _flatten(values)))
    if axis != 0:
        raise NotImplementedError("only axis=0 is supported in this stub")
    columns = list(zip(*values))
    return SimpleArray(statistics.pvariance(float(x) for x in column) for column in columns)


def average(values: Sequence[Number], weights: Sequence[Number] | None = None) -> float:
    values = [float(x) for x in values]
    if weights is None:
        return statistics.fmean(values)
    weights = [float(w) for w in weights]
    total_weight = sum(weights)
    if total_weight == 0:
        raise ZeroDivisionError("weights sum to zero")
    return float(sum(v * w for v, w in zip(values, weights)) / total_weight)


def allclose(a: Sequence[Number], b: Sequence[Number], atol: float = 1e-08) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(float(x) - float(y)) <= atol for x, y in zip(a, b))


def max(values: Sequence[Number]) -> float:  # type: ignore[override]
    return float(__builtins__["max"](float(x) for x in values))


def min(values: Sequence[Number]) -> float:  # type: ignore[override]
    return float(__builtins__["min"](float(x) for x in values))


def abs(values: Union[Number, complex, Sequence[Union[Number, complex]]]):  # type: ignore[override]
    if isinstance(values, (int, float, complex)):
        return float(__builtins__["abs"](values))
    return SimpleArray(__builtins__["abs"](x) for x in values)


def clip(values: Union[Number, Sequence[Number]], min_value: float, max_value: float):
    if isinstance(values, (int, float)):
        return float(
            builtins.max(
                builtins.min(float(values), max_value),
                min_value,
            )
        )
    return SimpleArray(
        builtins.max(builtins.min(float(x), max_value), min_value) for x in values
    )


def sort(values: Sequence[Number]) -> SimpleArray:
    return SimpleArray(sorted(values))


def argsort(values: Sequence[Number]) -> SimpleArray:
    return SimpleArray(sorted(range(len(values)), key=lambda idx: values[idx]))


def argmax(values: Sequence[Number]) -> int:
    max_index = 0
    max_value = float(values[0]) if values else 0.0
    for i, value in enumerate(values):
        val = float(value)
        if val > max_value:
            max_value = val
            max_index = i
    return max_index


def sqrt(value: Number) -> float:
    return math.sqrt(float(value))


def sin(value: Union[Number, Sequence[Number]]):
    if isinstance(value, (int, float)):
        return math.sin(float(value))
    return SimpleArray(math.sin(float(v)) for v in value)


def cos(value: Union[Number, Sequence[Number]]):
    if isinstance(value, (int, float)):
        return math.cos(float(value))
    return SimpleArray(math.cos(float(v)) for v in value)


def arctan2(y: Number, x: Number) -> float:
    return math.atan2(float(y), float(x))


def tanh(value: Union[Number, Sequence[Number]]):
    if isinstance(value, (int, float)):
        return math.tanh(float(value))
    return SimpleArray(math.tanh(float(v)) for v in value)


def exp(value: Union[Number, Sequence[Number]]):
    if isinstance(value, (int, float)):
        return math.exp(float(value))
    return SimpleArray(math.exp(float(v)) for v in value)


def arccos(value: Union[Number, Sequence[Number]]):
    if isinstance(value, (int, float)):
        return math.acos(float(value))
    return SimpleArray(math.acos(float(v)) for v in value)


def log(values: Union[Number, Sequence[Number]]):
    if isinstance(values, (int, float)):
        return math.log(float(values))
    return SimpleArray(math.log(float(v)) for v in values)


def log2(values: Union[Number, Sequence[Number]]):
    if isinstance(values, (int, float)):
        return math.log2(float(values))
    return SimpleArray(math.log2(float(v)) for v in values)


def sign(values: Union[Number, Sequence[Number]]):
    def _sign(x: float) -> float:
        if x > 0:
            return 1.0
        if x < 0:
            return -1.0
        return 0.0

    if isinstance(values, (int, float)):
        return _sign(float(values))
    return SimpleArray(_sign(float(v)) for v in values)


pi = math.pi


def linspace(start: float, stop: float, num: int, endpoint: bool = True) -> SimpleArray:
    if num <= 0:
        return SimpleArray([])
    if num == 1:
        return SimpleArray([float(stop if endpoint else start)])
    step_count = num - 1 if endpoint else num
    step = (stop - start) / step_count
    values = [start + i * step for i in range(num)]
    if endpoint:
        values[-1] = stop
    return SimpleArray(values)


def _flatten(values: Sequence) -> Iterator:
    for item in values:
        if isinstance(item, (list, tuple, SimpleArray)):
            yield from _flatten(item)
        else:
            yield item


class _LinalgModule:
    def norm(self, values: Sequence[Number], ord: int | None = None) -> float:
        if ord not in (None, 2):
            raise NotImplementedError("Only Euclidean norm is supported")
        if values and isinstance(values[0], (list, tuple, SimpleArray)):
            flattened = [float(x) for x in _flatten(values)]
            return math.sqrt(sum(val ** 2 for val in flattened))
        return math.sqrt(sum(float(x) ** 2 for x in values))

    def eigvalsh(self, matrix: Sequence[Sequence[Number]]) -> SimpleArray:
        # Jacobi eigenvalue algorithm for symmetric matrices.
        a = [[float(value) for value in row] for row in matrix]
        n = len(a)
        if n == 0:
            return SimpleArray([])
        # Protect against non-square matrices
        if any(len(row) != n for row in a):
            raise ValueError("Matrix must be square")

        def max_offdiag(mat: List[List[float]]) -> Tuple[int, int, float]:
            max_val = 0.0
            p = q = 0
            for i in range(n):
                for j in range(i + 1, n):
                    if abs(mat[i][j]) > abs(max_val):
                        max_val = mat[i][j]
                        p, q = i, j
            return p, q, max_val

        for _ in range(50):  # sufficient for the small matrices we use
            p, q, value = max_offdiag(a)
            if abs(value) < 1e-10:
                break
            theta = 0.5 * math.atan2(2 * value, a[q][q] - a[p][p])
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)

            app = a[p][p]
            aqq = a[q][q]
            apq = a[p][q]

            a[p][p] = cos_t**2 * app - 2 * sin_t * cos_t * apq + sin_t**2 * aqq
            a[q][q] = sin_t**2 * app + 2 * sin_t * cos_t * apq + cos_t**2 * aqq
            a[p][q] = a[q][p] = 0.0

            for r in range(n):
                if r not in (p, q):
                    arp = a[r][p]
                    arq = a[r][q]
                    a[r][p] = a[p][r] = cos_t * arp - sin_t * arq
                    a[r][q] = a[q][r] = sin_t * arp + cos_t * arq

        eigenvalues = [a[i][i] for i in range(n)]
        eigenvalues.sort()
        return SimpleArray(eigenvalues)


class _RandomModule:
    def __init__(self) -> None:
        self._rng = _random.Random(0)

    def seed(self, seed_value: int) -> None:
        self._rng.seed(seed_value)

    def random(self) -> float:
        return float(self._rng.random())

    def normal(self, loc: float = 0.0, scale: float = 1.0, size: Union[None, int, Tuple[int, ...]] = None):
        if size is None:
            return float(self._rng.gauss(loc, scale))
        if isinstance(size, int):
            return SimpleArray(self._rng.gauss(loc, scale) for _ in range(size))
        return SimpleArray(
            _filled_array(size, 0.0)  # type: ignore[arg-type]
        )

    def randn(self, *shape: int) -> SimpleArray:
        if len(shape) == 1:
            n = shape[0]
            return SimpleArray(self._rng.gauss(0, 1) for _ in range(n))
        if len(shape) == 2:
            rows, cols = shape
            return SimpleArray(
                SimpleArray(self._rng.gauss(0, 1) for _ in range(cols))
                for _ in range(rows)
            )
        raise NotImplementedError("randn supports at most two dimensions")

    def uniform(self, low: float = 0.0, high: float = 1.0, size: Union[None, int, Tuple[int, ...]] = None):
        if size is None:
            return float(self._rng.uniform(low, high))
        if isinstance(size, int):
            return SimpleArray(self._rng.uniform(low, high) for _ in range(size))
        total = _filled_array(size, 0.0)
        def _fill(target, depth):
            if depth == len(size) - 1:
                for i in range(len(target)):
                    target[i] = float(self._rng.uniform(low, high))
            else:
                for sub in target:
                    _fill(sub, depth + 1)
        _fill(total, 0)
        return total

    def choice(self, a: Union[int, Sequence], size: Union[None, int] = None, replace: bool = True):
        population = list(range(a)) if isinstance(a, int) else list(a)
        if not population:
            raise ValueError("a cannot be empty")
        if size is None:
            return population[self._rng.randrange(len(population))]
        if replace:
            return SimpleArray(population[self._rng.randrange(len(population))] for _ in range(size))
        if size > len(population):
            raise ValueError("Cannot take a larger sample than population when 'replace=False'")
        return SimpleArray(self._rng.sample(population, size))

    class RandomState:
        def __init__(self, seed_value: int) -> None:
            self._rng = _random.Random(seed_value)

        def randn(self, n: int) -> SimpleArray:
            return SimpleArray(self._rng.gauss(0, 1) for _ in range(n))


class _FFTModule:
    def fft(self, values: Sequence[Number]) -> SimpleArray:
        values = [complex(x) for x in values]
        n = len(values)
        result = []
        for k in range(n):
            total = 0j
            for t, value in enumerate(values):
                total += value * cmath.exp(-2j * math.pi * k * t / n)
            result.append(total)
        return SimpleArray(result)


linalg = _LinalgModule()
random = _RandomModule()
fft = _FFTModule()


def cov(matrix: Sequence[Sequence[Number]]) -> SimpleArray:
    rows = [array(row) for row in matrix]
    if not rows:
        return SimpleArray([])
    n = len(rows)
    cols = len(rows[0])
    means = [statistics.fmean(row[i] for row in rows) for i in range(cols)]
    denom = n - 1 if n > 1 else 1
    cov_matrix: List[List[float]] = []
    for i in range(cols):
        row = []
        for j in range(cols):
            value = sum((rows[k][i] - means[i]) * (rows[k][j] - means[j]) for k in range(n)) / denom
            row.append(float(value))
        cov_matrix.append(row)
    return SimpleArray(SimpleArray(r) for r in cov_matrix)


@contextmanager
def errstate(**kwargs):  # pragma: no cover
    yield


inf = float("inf")


ndarray = SimpleArray


__all__ = [
    "SimpleArray",
    "array",
    "zeros",
    "ones",
    "arange",
    "roll",
    "diag",
    "dot",
    "sum",
    "prod",
    "mean",
    "std",
    "var",
    "average",
    "allclose",
    "max",
    "min",
    "abs",
    "clip",
    "sort",
    "sqrt",
    "sin",
    "cos",
    "tanh",
    "exp",
    "arccos",
    "pi",
    "linspace",
    "linalg",
    "random",
    "fft",
    "cov",
    "inf",
]
