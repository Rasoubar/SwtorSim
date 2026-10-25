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
