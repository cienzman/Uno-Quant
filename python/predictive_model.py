def calculate_session_consumption(rate_per_usage: float, session_duration_s: float, avg_duration: float) -> float:
    """
    Phase 0: Scale consumption based on session duration relative to average duration.
    """
    if avg_duration and avg_duration > 0:
        duration_scale = session_duration_s / avg_duration
    else:
        duration_scale = 1.0  # Fallback for first session or missing average

    return rate_per_usage * duration_scale

def update_rate_belief(prior_mean: float, prior_var: float, observed_rate: float, likelihood_var: float = 25.0) -> tuple[float, float]:
    """
    Phase 1: Standard Bayesian update for Gaussian prior + Gaussian likelihood.
    Returns (posterior_mean, posterior_var).
    """
    # Prevent division by zero if variances get too small
    prior_var = max(prior_var, 0.0001)
    likelihood_var = max(likelihood_var, 0.0001)

    posterior_var = 1.0 / (1.0 / prior_var + 1.0 / likelihood_var)
    posterior_mean = posterior_var * (prior_mean / prior_var + observed_rate / likelihood_var)
    
    return posterior_mean, posterior_var

def apply_feedback_correction(estimated_qty: float, rate_per_usage: float, feedback_yes: bool) -> float:
    """
    Phase 2: Directional correction based on YES/NO micro-feedback.
    """
    if feedback_yes and estimated_qty < rate_per_usage * 0.8:
        # Model underestimates — pull up toward the threshold
        return estimated_qty + (rate_per_usage - estimated_qty) * 0.4
    elif not feedback_yes and estimated_qty >= rate_per_usage:
        # Model overestimates — push below the threshold
        return max(0.0, estimated_qty - (estimated_qty - rate_per_usage * 0.7) * 0.5)
    
    return estimated_qty
