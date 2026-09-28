# JUDGING.md · Mathematical Foundations of Judging & Normalization

This document provides the formal mathematical proof and operational specification for the judging algorithms in **Veritas**.

---

## 1. The Challenge with Raw Hackathon Scoring

Standard hackathon platforms employ simple arithmetic averages over raw scores. This introduces two structural biases:

1. **Judge Leniency / Harshness Bias:** A project assigned three strict judges (mean score 2.8) is severely penalized compared to an identical project assigned three generous judges (mean score 4.5).
2. **Uneven Coverage Artifacts:** At scale, projects receive varying numbers of evaluations (e.g. 2 reviews vs. 5 reviews). A project with a single 5.0 score should not trivially outrank a project with five reviews averaging 4.8.

---

## 2. Two-Way Fixed Effects Normalization (Empirical Bayes)

Veritas models every review composite score $Y_{ij}$ for project $i$ and judge $j$ as:

$$Y_{ij} = \mu + \alpha_i + \beta_j + \epsilon_{ij}$$

Where:
- $\mu \in \mathbb{R}$ is the global population mean.
- $\alpha_i \in \mathbb{R}$ is the true latent project quality.
- $\beta_j \in \mathbb{R}$ is the judge's leniency offset, constrained by:
  $$\sum_{j=1}^{J} \beta_j = 0$$
- $\epsilon_{ij} \sim \mathcal{N}(0, \sigma_\epsilon^2)$ is random noise.

### Alternating Least Squares (ALS) Estimation

We solve for $\hat{\alpha}_i$ and $\hat{\beta}_j$ iteratively via alternating conditional expectations:

1. **Project Quality Step:**
   $$\hat{\alpha}_i^{(t+1)} = \frac{1}{n_i} \sum_{j \in \mathcal{J}_i} \left( Y_{ij} - \mu - \hat{\beta}_j^{(t)} \right)$$

2. **Judge Leniency Step:**
   $$\hat{\beta}_j^{(t+1)} = \frac{1}{m_j} \sum_{i \in \mathcal{I}_j} \left( Y_{ij} - \mu - \hat{\alpha}_i^{(t+1)} \right)$$

3. **Centering Step:**
   $$\hat{\beta}_j^{(t+1)} \leftarrow \hat{\beta}_j^{(t+1)} - \frac{1}{J} \sum_{k=1}^J \hat{\beta}_k^{(t+1)}$$

Convergence occurs within 10 iterations ($||\Delta \alpha||_\infty < 10^{-6}$).

---

## 3. Efron-Morris Empirical Bayes Shrinkage

To address uneven coverage, we apply the James-Stein / Efron-Morris shrinkage estimator (1975). We compute:

$$\hat{\alpha}_i^{\text{shrunk}} = B_i \cdot \hat{\alpha}_i$$

Where the shrinkage factor $B_i \in [0, 1]$ is:

$$B_i = \frac{n_i}{n_i + k}$$

And $k$ is the ratio of residual variance to true project quality variance:

$$k = \frac{\hat{\sigma}_\epsilon^2}{\hat{\sigma}_\alpha^2}$$

### Final Calibrated Score

$$\text{Score}_i = \mu + B_i \cdot \hat{\alpha}_i$$

$$\text{SE}_i = \sqrt{\frac{\hat{\sigma}_\epsilon^2}{n_i + k}}$$

### Coverage Effect Table on Official Fixtures ($k \approx 0.81$):

| Reviews ($n_i$) | Retained Signal ($B_i$) | Standard Error ($\text{SE}_i$) | Interpretation |
| :---: | :---: | :---: | :--- |
| **1** | 55.2% | $\pm 0.44$ | Heavy shrinkage toward mean; prevents lucky 1-review outliers |
| **2** | 71.1% | $\pm 0.35$ | Moderate shrinkage; baseline confidence |
| **3** | 78.7% | $\pm 0.30$ | Strong confidence |
| **5** | 86.0% | $\pm 0.24$ | High confidence; reviews dominate shrinkage |

---

## 4. Bradley-Terry Pairwise Arena Model

In addition to rubric scores, Veritas implements pairwise head-to-head evaluation. The probability that project $i$ beats project $j$ is parameterized by latent skill $\pi_i > 0$:

$$P(i \succ j) = \frac{\pi_i}{\pi_i + \pi_j}$$

Given observed wins $w_{ij}$ and total comparisons $N_{ij} = w_{ij} + w_{ji}$, the log-likelihood is:

$$\ell(\boldsymbol{\pi}) = \sum_{i=1}^M \sum_{j \neq i} \left[ w_{ij} \ln \pi_i - N_{ij} \ln(\pi_i + \pi_j) \right]$$

### Minorization-Maximization (Hunter, 2004) Update:

$$\pi_i^{(t+1)} = \frac{W_i}{\sum_{j \neq i} \frac{N_{ij}}{\pi_i^{(t)} + \pi_j^{(t)}}}$$

Where $W_i = \sum_j w_{ij}$. Veritas normalizes the converged skill parameters to a scale of $[0, 100]$ for transparent interpretation.

---

## 5. Duplicate Submissions & Zero-Variance Edge Cases

- **Duplicate Submissions:** Detected via `(team_id, repo_url)` matching. Reviews from duplicate submissions are merged into a unified project node prior to model estimation.
- **Zero-Variance Judges:** A judge who assigns the identical score to every project introduces an additive shift $\beta_j$ but zero variance. Because our model does not divide by judge variance (unlike naive z-scoring), zero-variance judges do not cause division-by-zero crashes.
