"""The few statistics functions used in the A/B test (numpy + scipy only).

Convention everywhere: group 1 = control (/billing), group 2 = new page (/billing-2),
and every difference is "new page minus control".
"""
import numpy as np
from scipy import stats


def two_prop_ztest(x1, n1, x2, n2):
    """Two-sided z-test for the difference between two proportions.

    x = number of successes (orders), n = group size (sessions).
    Uses the POOLED standard error, because under H0 both groups share one true rate.
    Returns (z, p_value).
    """
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se
    p_value = 2 * stats.norm.sf(abs(z))  # both tails
    return float(z), float(p_value)


def diff_ci(x1, n1, x2, n2, level=0.95):
    """Confidence interval for p2 - p1 (normal approximation).

    Uses the UNPOOLED standard error, because a CI does not assume the rates are equal.
    Returns (diff, low, high).
    """
    p1, p2 = x1 / n1, x2 / n2
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z_crit = stats.norm.ppf(1 - (1 - level) / 2)  # 1.96 for 95%
    diff = p2 - p1
    return float(diff), float(diff - z_crit * se), float(diff + z_crit * se)


def bootstrap_diff_ci(a, b, n_boot=2000, seed=42, level=0.95):
    """Bootstrap confidence interval for mean(b) - mean(a).

    a, b = arrays with one value per session (for example revenue, or 0/1 for ordered).
    Why bootstrap: revenue per session is mostly zeros plus a few $49.99 values, so it is
    not bell-shaped. Resampling the sessions makes no assumption about the shape.
    Returns (diff, low, high).
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        # Draw each group again with replacement, same size as the original group.
        sample_a = rng.choice(a, size=len(a), replace=True)
        sample_b = rng.choice(b, size=len(b), replace=True)
        diffs[i] = sample_b.mean() - sample_a.mean()
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(diffs, [tail, 100 - tail])
    return float(b.mean() - a.mean()), float(low), float(high)


def srm_pvalue(n1, n2):
    """Sample ratio mismatch: chi-square test of the two group sizes against a 50/50 split.

    A very small p-value means the traffic split itself looks broken, and then the
    test result cannot be trusted.
    """
    return float(stats.chisquare([n1, n2]).pvalue)


def mde_two_prop(p_base, n_per_group, alpha=0.05, power=0.8):
    """Minimum detectable effect (absolute) for a two-proportion test.

    The smallest true lift this test could reliably find with the sample it had:
        (z_{1-alpha/2} + z_{power}) * sqrt(2 * p * (1 - p) / n)
    """
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    return float((z_alpha + z_power) * np.sqrt(2 * p_base * (1 - p_base) / n_per_group))


def prop_ci(x, n, level=0.95):
    """Confidence interval for ONE proportion (normal approximation). Returns (p, low, high).

    Only used to draw the whiskers on the charts.
    """
    p = x / n
    half = stats.norm.ppf(1 - (1 - level) / 2) * np.sqrt(p * (1 - p) / n)
    return float(p), float(p - half), float(p + half)
