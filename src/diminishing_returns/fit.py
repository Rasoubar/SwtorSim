"""DPS surface on the game's critical-rating curves.

At base mastery m0 and base power p0 the surface is

    DPS(c, m, p) = S(c) + (m - m0) * gM(c) + (p - p0) * gP(c)

S, gM, and gP are linear combinations of the sim's diminishing-return curve
for Critical Rating. Critical chance and critical damage use that curve; when
the two share a cap and a divisor, the basis is 1, the curve, and its square.
When they differ, critical damage is a second curve and the basis also
includes the product.

    dDPS/dCrit = S'(c)
    dDPS/dMastery = gM(c)
    dDPS/dPower = gP(c)

Each evaluated curve also carries its ordinary-least-squares standard error.
"""

from dataclasses import dataclass

import numpy as np

_CURVE_COUNT = 4


@dataclass(frozen=True)
class CritCurves:
    """Level-85 style caps and divisors for the two critical-rating curves."""

    level: int
    chance_cap: float
    chance_divisor: float
    damage_cap: float
    damage_divisor: float

    @property
    def shared(self) -> bool:
        """True when chance and damage are the same function of rating."""
        return bool(
            np.isclose(self.chance_cap, self.damage_cap)
            and np.isclose(self.chance_divisor, self.damage_divisor)
        )


@dataclass
class SurfaceFit:
    """Coefficients and covariance for one relic variant."""

    curves: CritCurves
    coefficients: np.ndarray
    covariance: np.ndarray
    residual_std: float

    def evaluate(self, crit) -> "SurfaceValues":
        """Evaluates level, slopes, and their 1σ standard errors."""
        crit = np.asarray(crit, dtype=float).reshape(-1)
        values, derivs = _features(crit, self.curves)
        level, mastery, power = self.coefficients
        width = level.shape[0]
        return SurfaceValues(
            crit=crit,
            dps=values @ level,
            dps_per_crit=derivs @ level,
            dps_per_mastery=values @ mastery,
            dps_per_power=values @ power,
            dps_sigma=_spread(values, self.covariance[:width, :width]),
            dps_per_crit_sigma=_spread(derivs, self.covariance[:width, :width]),
            dps_per_mastery_sigma=_spread(values, self.covariance[width:2 * width, width:2 * width]),
            dps_per_power_sigma=_spread(values, self.covariance[2 * width:, 2 * width:]),
        )


@dataclass
class SurfaceValues:
    """DPS, its three stat slopes, and a 1σ standard error for each."""

    crit: np.ndarray
    dps: np.ndarray
    dps_per_crit: np.ndarray
    dps_per_mastery: np.ndarray
    dps_per_power: np.ndarray
    dps_sigma: np.ndarray
    dps_per_crit_sigma: np.ndarray
    dps_per_mastery_sigma: np.ndarray
    dps_per_power_sigma: np.ndarray


def crit_curve(rating, cap: float, divisor: float, level: int):
    """Returns the diminishing-return value and its derivative with respect to rating.

    This is the same expression as calc_dr, including at zero rating, plus
    d/dr = (cap - value) * (-ln(1 - 0.01/cap)) / (divisor * level).
    """
    rating = np.asarray(rating, dtype=float)
    base = 1.0 - (0.01 / cap)
    powered = base ** (rating / (divisor * level))
    value = cap * (1.0 - powered)
    derivative = (cap * powered) * (-np.log(base)) / (divisor * level)
    return value, derivative


def fit_surface(
    crit,
    mastery,
    power,
    dps,
    mastery0: float,
    power0: float,
    curves: CritCurves,
) -> SurfaceFit:
    """Fits the crit-curve surface and the coefficient covariance."""
    _validate_curves(curves)
    crit = np.asarray(crit, dtype=float).reshape(-1)
    mastery = np.asarray(mastery, dtype=float).reshape(-1)
    power = np.asarray(power, dtype=float).reshape(-1)
    dps = np.asarray(dps, dtype=float).reshape(-1)
    n = crit.shape[0]
    if not (mastery.shape[0] == power.shape[0] == dps.shape[0] == n):
        raise ValueError("crit, mastery, power, and dps must have the same length.")
    if not np.all(np.isfinite(dps)):
        raise ValueError("dps contains non-finite values.")

    values, _derivs = _features(crit, curves)
    mastery_delta = (mastery - mastery0)[:, None]
    power_delta = (power - power0)[:, None]
    design = np.hstack((values, mastery_delta * values, power_delta * values))
    n_coeff = design.shape[1]
    if n <= n_coeff:
        raise ValueError(
            f"Need more than {n_coeff} samples to fit the crit curves, got {n}."
        )

    scale = np.linalg.norm(design, axis=0)
    scale[scale == 0.0] = 1.0
    scaled = design / scale
    beta_scaled, _, _, _ = np.linalg.lstsq(scaled, dps, rcond=None)
    beta = beta_scaled / scale
    residual = dps - design @ beta
    dof = n - n_coeff
    sigma2 = float(np.dot(residual, residual) / dof)
    gram = scaled.T @ scaled
    try:
        cov_scaled = sigma2 * np.linalg.inv(gram)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Crit-curve design is singular, so the fit has no standard error.") from exc
    covariance = cov_scaled / np.outer(scale, scale)
    return SurfaceFit(
        curves=curves,
        coefficients=beta.reshape(3, values.shape[1]),
        covariance=covariance,
        residual_std=float(np.sqrt(np.mean(residual**2))),
    )


def _features(rating, curves: CritCurves):
    """Basis values and derivatives. Columns are level terms, in fit order."""
    chance, chance_slope = crit_curve(
        rating, curves.chance_cap, curves.chance_divisor, curves.level
    )
    if curves.shared:
        values = np.column_stack((np.ones_like(chance), chance, chance**2))
        derivs = np.column_stack((np.zeros_like(chance), chance_slope, 2.0 * chance * chance_slope))
        return values, derivs

    damage, damage_slope = crit_curve(
        rating, curves.damage_cap, curves.damage_divisor, curves.level
    )
    product = chance * damage
    product_slope = chance_slope * damage + chance * damage_slope
    values = np.column_stack((np.ones_like(chance), chance, damage, product))
    derivs = np.column_stack((
        np.zeros_like(chance), chance_slope, damage_slope, product_slope
    ))
    return values, derivs


def _spread(features: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    """Pointwise standard error of features @ beta for one coefficient block."""
    projected = features @ covariance
    variance = np.sum(projected * features, axis=1)
    return np.sqrt(np.maximum(variance, 0.0))


# Keeps the square-root slope finite at zero crit: 1 / (2 sqrt(c + shift)).
SQRT_SHIFT = 1000.0


def _sqrt_basis(crit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Values and crit derivatives of 1, sqrt(c + 1000), c, c^2."""
    shifted = np.sqrt(crit + SQRT_SHIFT)
    values = np.column_stack((np.ones_like(crit), shifted, crit, crit**2))
    derivs = np.column_stack((
        np.zeros_like(crit),
        0.5 / shifted,
        np.ones_like(crit),
        2.0 * crit,
    ))
    return values, derivs


@dataclass
class SqrtPolynomialFit:
    """Level, mastery slope, and power slope share one crit curve.

    At the build's mastery and power,

        DPS(c) = b0 + b1 sqrt(c + 1000) + b2 c + b3 c^2

    The mastery and power slopes use that same shape in crit. The crit slope
    is the derivative of the level, evaluated at the build.
    """

    coefficients: np.ndarray
    covariance: np.ndarray
    residual_std: float

    def evaluate(self, crit) -> SurfaceValues:
        """Evaluates level, slopes, and their 1σ standard errors."""
        crit = np.asarray(crit, dtype=float).reshape(-1)
        if np.any(crit < 0.0):
            raise ValueError("Crit rating must be non-negative for the square-root fit.")
        basis, deriv = _sqrt_basis(crit)
        zeros = np.zeros_like(basis)
        level = np.hstack((basis, zeros, zeros))
        crit_slope = np.hstack((deriv, zeros, zeros))
        mastery_slope = np.hstack((zeros, basis, zeros))
        power_slope = np.hstack((zeros, zeros, basis))
        beta = self.coefficients
        return SurfaceValues(
            crit=crit,
            dps=level @ beta,
            dps_per_crit=crit_slope @ beta,
            dps_per_mastery=mastery_slope @ beta,
            dps_per_power=power_slope @ beta,
            dps_sigma=_spread(level, self.covariance),
            dps_per_crit_sigma=_spread(crit_slope, self.covariance),
            dps_per_mastery_sigma=_spread(mastery_slope, self.covariance),
            dps_per_power_sigma=_spread(power_slope, self.covariance),
        )


def fit_sqrt_polynomial(crit, mastery, power, dps, mastery0: float, power0: float) -> SqrtPolynomialFit:
    """Fits the square-root crit curve for the level and for both stat slopes."""
    crit = np.asarray(crit, dtype=float).reshape(-1)
    mastery = np.asarray(mastery, dtype=float).reshape(-1)
    power = np.asarray(power, dtype=float).reshape(-1)
    dps = np.asarray(dps, dtype=float).reshape(-1)
    n = crit.shape[0]
    if not (mastery.shape[0] == power.shape[0] == dps.shape[0] == n):
        raise ValueError("crit, mastery, power, and dps must have the same length.")
    if np.any(crit < 0.0) or not np.all(np.isfinite(dps)):
        raise ValueError("crit must be non-negative and dps must be finite.")
    if n <= 12:
        raise ValueError(f"Need more than 12 samples to fit the square-root polynomial, got {n}.")

    basis, _deriv = _sqrt_basis(crit)
    mastery_delta = (mastery - mastery0)[:, None]
    power_delta = (power - power0)[:, None]
    design = np.hstack((basis, mastery_delta * basis, power_delta * basis))
    scale = np.linalg.norm(design, axis=0)
    scale[scale == 0.0] = 1.0
    scaled = design / scale
    beta_scaled, _, _, _ = np.linalg.lstsq(scaled, dps, rcond=None)
    beta = beta_scaled / scale
    residual = dps - design @ beta
    dof = n - design.shape[1]
    sigma2 = float(np.dot(residual, residual) / dof)
    try:
        covariance = sigma2 * np.linalg.inv(scaled.T @ scaled) / np.outer(scale, scale)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Square-root design is singular, so the fit has no standard error.") from exc
    return SqrtPolynomialFit(
        coefficients=beta,
        covariance=covariance,
        residual_std=float(np.sqrt(np.mean(residual**2))),
    )


def _validate_curves(curves: CritCurves) -> None:
    if isinstance(curves.level, bool) or not isinstance(curves.level, int) or curves.level < 1:
        raise ValueError("Crit curve level must be a positive integer.")
    for name, value in (
        ("chance_cap", curves.chance_cap),
        ("damage_cap", curves.damage_cap),
    ):
        if value <= 0.01:
            raise ValueError(f"{name} must be greater than 0.01.")
    for name, value in (
        ("chance_divisor", curves.chance_divisor),
        ("damage_divisor", curves.damage_divisor),
    ):
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
    if _features(np.array([0.0, 1.0]), curves)[0].shape[1] > _CURVE_COUNT:
        raise ValueError("Crit curve basis is wider than expected.")


# Fraction of fights inside each local window. Wider windows smooth more and
# hold the slope level for longer at the ends of the sweep.
LOESS_SPAN = 0.8
_RESIDUAL_GRID = 51


@dataclass
class LoessFit:
    """Local-linear LOESS of the same mastery and power surface.

    Around a crit value c0 the fit is

        DPS = a + b (c - c0) + gM (m - m0) + gP (p - p0)

    with tricube weights in crit. Then a is DPS, b is the crit slope, and gM
    and gP are the mastery and power slopes. The 1σ bands are the sandwich
    standard errors of those four coefficients.
    """

    crit: np.ndarray
    mastery: np.ndarray
    power: np.ndarray
    dps: np.ndarray
    mastery0: float
    power0: float
    span: float
    residual_std: float
    _sigma2: float

    def evaluate(self, crit) -> SurfaceValues:
        """Evaluates level, slopes, and their 1σ standard errors at each crit."""
        query = np.asarray(crit, dtype=float).reshape(-1)
        beta, meat = _loess_coefficients(
            self.crit, self.mastery, self.power, self.dps,
            query, self.mastery0, self.power0, self.span,
        )
        scale = np.sqrt(self._sigma2)
        spread = scale * np.sqrt(np.maximum(meat, 0.0))
        return SurfaceValues(
            crit=query,
            dps=beta[:, 0],
            dps_per_crit=beta[:, 1],
            dps_per_mastery=beta[:, 2],
            dps_per_power=beta[:, 3],
            dps_sigma=spread[:, 0],
            dps_per_crit_sigma=spread[:, 1],
            dps_per_mastery_sigma=spread[:, 2],
            dps_per_power_sigma=spread[:, 3],
        )


def fit_loess(
    crit,
    mastery,
    power,
    dps,
    mastery0: float,
    power0: float,
    span: float = LOESS_SPAN,
) -> LoessFit:
    """Fits a LOESS surface. Crit is sorted once; each query builds its own window."""
    if isinstance(span, bool) or not isinstance(span, (int, float)) or not 0.0 < float(span) <= 1.0:
        raise ValueError("LOESS span must be greater than 0 and at most 1.")
    crit = np.asarray(crit, dtype=float).reshape(-1)
    mastery = np.asarray(mastery, dtype=float).reshape(-1)
    power = np.asarray(power, dtype=float).reshape(-1)
    dps = np.asarray(dps, dtype=float).reshape(-1)
    n = crit.shape[0]
    if not (mastery.shape[0] == power.shape[0] == dps.shape[0] == n):
        raise ValueError("crit, mastery, power, and dps must have the same length.")
    if not np.all(np.isfinite(dps)):
        raise ValueError("dps contains non-finite values.")
    if n < 8:
        raise ValueError(f"Need at least 8 samples for LOESS, got {n}.")

    order = np.argsort(crit, kind="mergesort")
    fit = LoessFit(
        crit=crit[order],
        mastery=mastery[order],
        power=power[order],
        dps=dps[order],
        mastery0=float(mastery0),
        power0=float(power0),
        span=float(span),
        residual_std=0.0,
        _sigma2=0.0,
    )
    grid = np.linspace(float(fit.crit[0]), float(fit.crit[-1]), _RESIDUAL_GRID)
    beta, _meat = _loess_coefficients(
        fit.crit, fit.mastery, fit.power, fit.dps,
        grid, fit.mastery0, fit.power0, fit.span,
    )
    predicted = (
        np.interp(crit, grid, beta[:, 0])
        + (mastery - mastery0) * np.interp(crit, grid, beta[:, 2])
        + (power - power0) * np.interp(crit, grid, beta[:, 3])
    )
    residual = dps - predicted
    fit.residual_std = float(np.sqrt(np.mean(residual**2)))
    fit._sigma2 = float(np.dot(residual, residual) / n)
    return fit


def _loess_coefficients(crit, mastery, power, dps, query, mastery0, power0, span):
    """Returns coefficients and sandwich diagonals at each query crit."""
    n = crit.shape[0]
    k = min(n, max(8, int(np.ceil(span * n))))
    beta = np.empty((query.shape[0], 4))
    meat = np.empty((query.shape[0], 4))
    for index, c0 in enumerate(query):
        beta[index], meat[index] = _loess_at(
            crit, mastery, power, dps, float(c0), mastery0, power0, k
        )
    return beta, meat


def _loess_at(crit, mastery, power, dps, c0, mastery0, power0, k):
    left, right = _neighborhood(crit, c0, k)
    window = slice(left, right)
    cw = crit[window]
    half_width = max(c0 - float(cw[0]), float(cw[-1]) - c0)
    if half_width <= 0.0:
        raise ValueError("LOESS window has no crit range, so the crit slope is undefined.")
    distance = np.abs(cw - c0) / half_width
    weight = (1.0 - np.minimum(distance, 1.0) ** 3) ** 3
    weight[distance >= 1.0] = 0.0
    keep = weight > 0.0
    if int(keep.sum()) < 8:
        raise ValueError("LOESS window has fewer than 8 fights with positive weight.")
    design = np.column_stack((
        np.ones(int(keep.sum())),
        cw[keep] - c0,
        mastery[window][keep] - mastery0,
        power[window][keep] - power0,
    ))
    weighted = weight[keep]
    response = dps[window][keep]
    gram = design.T @ (weighted[:, None] * design)
    moment = design.T @ ((weighted**2)[:, None] * design)
    try:
        beta = np.linalg.solve(gram, design.T @ (weighted * response))
        inverse = np.linalg.inv(gram)
    except np.linalg.LinAlgError as exc:
        raise ValueError("LOESS design is singular at this crit value.") from exc
    sandwich = inverse @ moment @ inverse
    return beta, np.diag(sandwich)


def _neighborhood(crit, c0: float, k: int) -> tuple[int, int]:
    """Index range of the k crit samples closest to c0. Crit must be sorted."""
    n = crit.shape[0]
    right = int(np.searchsorted(crit, c0, side="right"))
    left = right
    while right - left < k:
        if left == 0:
            return 0, k
        if right == n:
            return n - k, n
        if (c0 - float(crit[left - 1])) <= (float(crit[right]) - c0):
            left -= 1
        else:
            right += 1
    return left, right
