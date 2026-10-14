import math
import numpy as np
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist


def model(z_hat, sd, f, n, center, L, eiv, idx_c=None, idx_b=None):
    T = z_hat.shape[0]
    eta = numpyro.sample("eta", dist.HalfNormal(2.0))
    ell = numpyro.sample("ell", dist.LogNormal(math.log(1.1), 0.5))
    mu0 = numpyro.sample("mu0", dist.Normal(0.0, 3.0))
    mu1 = numpyro.sample("mu1", dist.HalfNormal(3.0))
    beta = numpyro.sample(
        "beta", dist.Normal(0.0, 1.0).expand([M_BASIS]).to_event(1))   # noqa: F821 — the engine's module constant, as in the record
    tau = numpyro.sample("tau", dist.HalfNormal(1.0))
    if eiv:
        z_raw = numpyro.sample(
            "z_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
        z = z_hat + sd * z_raw          # non-centered z_t ~ N(z_hat, sd), as the record
    else:
        z = z_hat
    phi, w = hsgp_basis(z, center, L)                                     # noqa: F821 — the engine's functions, as in the record
    g = mu0 + mu1 * z + phi @ (se_sqrt_spd(w, eta, ell) * beta)           # noqa: F821
    # D1: partial centring by the counts (the index sets static, computed in run_inference)
    if idx_c is None or idx_b is None:      # the record's form when no index sets are passed (every cell non-centred)
        u_raw = numpyro.sample("u_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
        logits = g + tau * u_raw
    else:
        logits = g
        if len(idx_b):
            u_raw = numpyro.sample(
                "u_raw", dist.Normal(0.0, 1.0).expand([int(len(idx_b))]).to_event(1))
            logits = logits.at[jnp.asarray(idx_b)].add(tau * u_raw)          # boundary cells: non-centred, as the record
        if len(idx_c):
            eta_c = numpyro.sample(
                "eta_c", dist.Normal(g[jnp.asarray(idx_c)], tau).to_event(1))  # interior cells: CENTRED on the curve
            logits = logits.at[jnp.asarray(idx_c)].set(eta_c)
    numpyro.sample(
        "f", dist.Binomial(total_count=n, logits=logits), obs=f)


