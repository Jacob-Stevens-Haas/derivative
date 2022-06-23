# Run tests that checks basic derivative examples. Use warnings to denote a mathematical failure.
import warnings
import numpy as np
import pytest
from derivative import dxdt, smooth_x, methods
from derivative.differentiation import _gen_method


def default_args(kind):
    """ The assumption is that the function will have dt = 1/100 over a range of 1 and not vary much. The goal is to
     to set the parameters such that we obtain effective derivatives under these conditions.
    """
    if kind == 'spectral':
        # frequencies should be guaranteed to be between 0 and 50 (a filter will reduce bad outliers)
        return {'filter': np.vectorize(lambda w: 1 if abs(w) < 10 else 0)}
    elif kind == 'spline':
        return {'s': 0.1}
    elif kind == 'trend_filtered':
        return {'order': 0, 'alpha': .01, 'max_iter': 1e3}
    elif kind == 'finite_difference':
        return {'k': 1}
    elif kind == 'savitzky_golay':
        return {'left': 5, 'right': 5, 'order': 3, 'iwindow': True}
    elif kind == 'kalman':
        return {'alpha': .05}
    else:
        raise ValueError('Unimplemented default args for kind {}.'.format(kind))


class NumericalExperiment:
    def __init__(self, fn, fn_str, t, kind, args):
        self.fn = fn
        self.fn_str = fn_str
        self.t = t
        self.kind = kind
        self.kwargs = args
        self.axis = 1

    def set_axis(self, axis):
        self.axis = axis

    def run(self):
        return dxdt(self.fn(self.t), self.t, self.kind, self.axis, **self.kwargs)


def compare(experiment, truth, median_tol, std_tol):
    """ Compare a numerical experiment to theoretical expectations. Issue warnings for derivative methods that fail,
    use asserts for implementation requirements.
    """
    values = experiment.run()
    message_main = "In {} dxdt applied to {}, ".format(experiment.kind, experiment.fn_str)
    message_sub = "output length of {} =/= expected length of {}.".format(len(values), len(truth))
    assert len(values) == len(truth), message_main + message_sub
    if len(values) > 0:
        residual = (values-truth)/len(values)
        # Median is robust to outliers
        if np.abs(np.median(residual)) > median_tol:
            message_sub = "residual median {0} exceeds tolerance of {1}.".format(np.median(residual), median_tol)
            warnings.warn(message_main + message_sub, UserWarning)
        # But make sure outliers are also looked at
        if np.abs(np.std(residual)) > std_tol:
            message_sub = "residual standard deviation {0} exceeds tolerance of {1}.".format(np.std(residual), std_tol)
            warnings.warn(message_main + message_sub)


# Check that numbers are returned
# ===============================
def test_notnan():
    t = np.linspace(0, 1, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: np.random.randn(*t1.shape), 'f(t) = t', t, m, default_args(m))
        values = nexp.run()
        message = "In {} dxdt applied to {}, np.nan returned instead of float.".format(nexp.kind, nexp.fn_str)
        assert not np.any(np.isnan(values)), message


# Test some basic functions
# =========================
def test_constant_fn1():
    t = np.linspace(0, 1, 100)
    for m in methods:
        if m == 'trend_filtered':
            # Add noise to avoid all zeros non-convergence warning for sklearn lasso
            nexp = NumericalExperiment(lambda t1: np.ones_like(t1) + np.random.randn(*t1.shape) * 1e-9, 'f(t) = 1', t,
                                       m, default_args(m))
        else:
            nexp = NumericalExperiment(lambda t: np.ones_like(t), 'f(t) = 1', t, m, default_args(m))
        compare(nexp, np.zeros_like(t), 1e-2, 1e-1)


def test_constant_fn2():
    t = np.linspace(-1, 0, 100)
    for m in methods:
        if m == 'trend_filtered':
            # Add noise to avoid all zeros non-convergence warning for sklearn lasso
            nexp = NumericalExperiment(lambda t1: np.random.randn(*t1.shape) * 1e-9, 'f(t) = 1', t, m, default_args(m))
        else:
            nexp = NumericalExperiment(lambda t: np.zeros_like(t), 'f(t) = 1', t, m, default_args(m))
        compare(nexp, np.zeros_like(t), 1e-2, 1e-1)


def test_linear_fn1():
    t = np.linspace(0, 1, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: t1, 'f(t) = t', t, m, default_args(m))
        compare(nexp, np.ones_like(t), 1e-2, 1e-1)


def test_linear_fn2():
    t = np.linspace(-1, 0, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: 2 * t1 + 1, 'f(t) = 2t+1', t, m, default_args(m))
        compare(nexp, 2*np.ones_like(t), 1e-2, 1e-1)


def test_linear_fn3():
    t = np.linspace(-0.5, 0.5, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: -1 * t1, 'f(t) = t', t, m, default_args(m))
        compare(nexp, -1*np.ones_like(t), 1e-2, 1e-1)


def test_polyn_fn():
    t = np.linspace(0, 1, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: t1 ** 2 - t1 + np.ones_like(t1), 'f(t) = t^2-t+1', t, m, default_args(m))
        compare(nexp, 2*t - np.ones_like(t), 1e-2, 1e-1)


def test_trig_fn():
    t = np.linspace(0, 1, 100)
    for m in methods:
        nexp = NumericalExperiment(lambda t1: np.sin(t1) + np.ones_like(t1) / 2, 'f(t) = sin(t)+1/2', t, m,
                                   default_args(m))
        compare(nexp, np.cos(t), 1e-2, 1e-1)


def test_smoothing_x():
    t = np.linspace(0, 1, 100)
    x = np.sin(t) + np.random.normal(size=t.shape)
    method = _gen_method(x, t, kind="kalman", axis=1, alpha=1.0)
    x_est = method.x(x, t)
    # MSE
    assert np.linalg.norm(x_est - np.sin(t)) ** 2 / len(t) < 1e-1


def test_smoothing_functional():
    t = np.linspace(0, 1, 100)
    x = np.sin(t) + np.random.normal(size=t.shape)
    x_est = smooth_x(x, t, kind="kalman", axis=1, alpha=1.0)
    # MSE
    assert np.linalg.norm(x_est - np.sin(t)) ** 2 / len(t) < 1e-1


@pytest.fixture
def clean_gen_method_cache():
    _gen_method.cache_clear()
    yield
    _gen_method.cache_clear()


def test_gen_method_caching(clean_gen_method_cache):
    x = np.ones(3)
    t = np.arange(3)
    expected = _gen_method(x, t, "finite_difference", 1, k=1)
    result = _gen_method(x, t, "finite_difference", 1, k=1)
    assert _gen_method.cache_info().hits == 1
    assert _gen_method.cache_info().misses == 1
    assert _gen_method.cache_info().currsize == 1
    assert id(expected) == id(result)


def test_gen_method_kwarg_caching(clean_gen_method_cache):
    x = np.ones(3)
    t = np.arange(3)
    expected = _gen_method(x, t, "finite_difference", 1, k=1)
    # different variants => cache misses
    result = _gen_method(x, t, "finite_difference", axis=1, k=1)
    _gen_method(x, t, kind="finite_difference", axis=1, k=1)
    assert _gen_method.cache_info().hits == 0
    assert _gen_method.cache_info().misses == 3
    assert _gen_method.cache_info().currsize == 3
    assert id(expected) != id(result)


@pytest.fixture
def kalman_method():
    x = np.ones(3)
    t = np.arange(3)
    method = _gen_method(x, t, "kalman", 1, alpha=1.0)
    method._global.cache_clear()
    yield x, t, method
    method._global.cache_clear()


def test_kalman_dglobal_caching(kalman_method):
    # make sure we're not recomputing expensive _global() method
    x, t, method = kalman_method
    method.x(x, t)
    method.d(x, t)
    assert method._global.cache_info().hits == 1
    assert method._global.cache_info().misses == 1
    assert method._global.cache_info().currsize == 1
