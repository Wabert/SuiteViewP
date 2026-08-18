# ABR Detailed Benefit Explanation — Disclosure Framework & Letter Template

**Status:** DRAFT for Legal/Compliance and Actuarial review — do not send to a
policyholder until the wording is cleared.
**Companion code:** `suiteview/abrquote/core/abr_explanation.py` generates the
standard explanation letter. **Part 3 below mirrors the app letter as of
2026-08-18** (always full acceleration; life-expectancy figures omitted per
business decision — see Part 4).
**Reference letters:** `ABR CLM UE236383(A).docx` (7/24/2026) and
`ABR_Benefit_Explanation_UE236383_*.docx` (generated) in this folder.

---

## Part 1 — Disclosure Principles

The governing regulatory framework is the **NAIC Accelerated Benefits Model
Regulation (#620)** (and the state/Interstate Compact standards derived from
it). Key facts that shape what we do and don't provide:

1. **§6.D (Effect of the Benefit Payment)** — when acceleration is requested,
   the insurer *must* send a statement showing the effect of the payment on the
   policy's cash value, death benefit, premium, policy loans and liens, plus
   warnings that the benefit **may be taxable** and **may affect Medicaid or
   other government-benefit eligibility**. Our explanation letter should always
   carry these two warnings — the current drafts omit them.
2. **§10.A(2) (Actuarial Standards)** — the present-value approach must use an
   interest rate "disclosed in the contract or actuarial memorandum," capped at
   the greater of the 90-day T-bill yield or the maximum statutory adjustable
   policy loan rate. This means **the interest rate and its basis are properly
   disclosable to the policyholder** — and our rider says the same thing.
3. **§11.A (Actuarial Disclosure)** — the *methodology* (bases and procedures
   used to calculate benefits) is described in an actuarial memorandum filed
   with the regulator and maintained in company files, "available for
   examination **by the commissioner** upon request." The model regulation
   contemplates regulator review of the detailed method — **not** delivery of
   the actuarial memorandum, work papers, or modified mortality tables to the
   policyholder. Our correct answer to "give me the modified table and the
   worksheet" is: here is every component and dollar figure, the detailed
   method is on file with the insurance regulator, and you may contact your
   Department of Insurance if you want an independent review.

From these, the working rule:

> **Disclose every *input the customer could verify* and every *dollar of the
> result*. Do not disclose the individualized medical-underwriting work product
> (the modified mortality table, its multipliers/flat extras, or the clinical
> judgments behind them).**

### Why the line sits there

* The base table (2008 VBT), the 75% multiple, the improvement scale, the
  interest-rate basis, the rider formula, and all the dollar amounts are either
  public, contractual, or required disclosures. Sharing them costs nothing and
  answers most of the customer's legitimate questions.
* The modified mortality table **is** the medical underwriting decision. The
  month-by-month calculation grid embeds the modified q(x) values, so producing
  "the complete calculation worksheet" at monthly granularity is equivalent to
  handing over the modified table. That is proprietary actuarial/underwriting
  work product, it contains judgments derived from protected health
  information, and disclosing the specific debits invites line-item clinical
  litigation of each factor ("my condition should be worth a bigger
  multiplier") that the claim process is not designed to adjudicate.
* The **summary worksheet** (PVFB, PVFP, PVFDivs, discount, fees, floor) does
  *not* reveal the table — totals cannot be inverted to monthly rates — so it
  is safe and it fully reconciles the offer to the penny.

---

## Part 2 — Decision Matrix for the Eleven Requests

| # | Request | Decision | Response |
|---|---------|----------|----------|
| 1 | Name/edition/source of industry mortality table | **Disclose** | 75% multiple of the 2008 Valuation Basic Table (VBT), published by the Society of Actuaries; varies by sex and smoking status. |
| 2 | The modified mortality table itself | **Decline — explain** | Describe how it is developed (medical review → adjustments to the base table) and its overall effect. The table itself is confidential medical-underwriting work product; the methodology is on file with the insurance regulator. |
| 3 | Multipliers, ratings, underwriting factors | **Structure yes, values no** | Disclose the *form* of adjustment (a table-rating multiple and/or a flat additional mortality amount, plus the 1%/yr improvement to age 105). Do not disclose the specific values assigned to this insured. |
| 4 | Methodology behind the projected life expectancy | **Disclose conceptually** | LE is an *output* of the modified table (sum of monthly survival probabilities), not an input to the benefit. Decision 2026-08-18: LE figures are omitted from the letter entirely (see Part 4). |
| 5 | Interest/discount rate | **Disclose fully** | State the exact rate, the index basis (Moody's Corporate Bond Yield Average, the same index used for the maximum policy loan rate), and the rider's cap (greater of 90-day T-bill yield or maximum adjustable policy loan rate). |
| 6 | Eligible Death Benefit | **Disclose** | Exact dollar amount (user-entered eligible DB for Option B policies). |
| 7 | Amount/percentage requested to accelerate | **Disclose** | Always presented as a full acceleration (100%). |
| 8 | Actuarial discount in $ and % | **Disclose $** | Discount = Amount Accelerated − (PVFB − PVFP + PVFDivs). Shown as an explicit worksheet row in dollars. |
| 9 | Administrative charge, policy debt adjustment | **Disclose** | Itemize each (admin charge varies by state — $100 FL / $250 elsewhere, capped at $500; any outstanding policy debt). Required by §6 anyway. |
| 10 | Complete step-by-step worksheet | **Summary level only** | Provide the component-level worksheet that reconciles exactly to the offer. Decline the month-by-month projection (it embeds the modified table — see Part 1). |
| 11 | Policy provisions governing each assumption | **Disclose** | Quote the rider's actuarial-discount and interest-rate provisions verbatim, cite the rider form number, and offer a copy of the rider. |

---

## Part 3 — Letter Template

Square brackets = fill per claim. {Curly braces} = optional blocks, include per
the guidance notes that follow the template.

---

> [LETTERHEAD]
> [Date]
>
> [Policyholder Name]
> [Street Address]
> [City, State ZIP]
>
> **RE: Accelerated Benefit — Policy [Number]**
>
> Dear [Policyholder Name]:
>
> This letter responds to your [date] correspondence regarding the Accelerated
> Benefit available under your policy and addresses each of your questions
> about how the benefit amount was determined. The calculation involves
> several actuarial components; the sections below describe each of them and
> show the figures used in this determination.
>
> **Why qualifying for the benefit does not itself determine the amount**
>
> The Accelerated Death Benefit Rider is not a disability or income-replacement
> benefit. It is an early payment of the policy's *death benefit*: when the
> rider's eligibility conditions are met, a portion of the death benefit that
> would otherwise be paid in the future can be paid now, reduced by an
> actuarial discount that reflects how early it is being paid.
>
> Eligibility and amount are therefore determined by different things.
> Eligibility depends on the condition described in the rider [e.g., the loss
> of the ability to perform activities of daily living]. The *amount*, however,
> depends on how significantly the insured's condition affects expected
> **mortality** — the likelihood and timing of death — because that is what
> determines how early the death benefit is being paid. Some conditions
> profoundly affect daily functioning (**morbidity**) while having only a
> modest effect on expected **mortality**. In those situations the
> rider's conditions for making a claim are met, but the actuarial value of
> paying the death benefit early is small. Based on the medical documentation
> reviewed, that is the situation here: the conditions identified
> [— condition summary —] were determined to significantly affect daily
> functioning but not to substantially affect expected mortality.
>
> The sooner the death benefit is expected to be paid, the less it must be
> reduced for being paid early, and the larger the amount that can be advanced
> today. Conversely, when expected mortality changes only modestly, the benefit
> is expected further in the future, a larger reduction applies, and the
> accelerated amount is smaller.
>
> **The mortality basis used in the calculation**
>
> * **Industry table (your request #1):** The standard-risk basis is a 75%
>   multiple of the **2008 Valuation Basic Table (VBT)**, an industry mortality
>   table published by the Society of Actuaries, which varies by sex and
>   smoking status. A mortality-improvement adjustment of 1% per year, up to
>   attained age 105, is applied.
> * **Modified table (your requests #2 and #3):** Our Medical Director's
>   Office reviews the medical documentation submitted with the claim and
>   adjusts the standard table to reflect the insured's specific condition.
>   The adjustment takes the form of a rating multiple applied to the table
>   and/or a flat additional mortality amount. This modified mortality table
>   is the primary driver of the calculation: it sets the year-by-year
>   likelihood of the claim, which determines the present value of the future
>   death benefit and of the future premiums.
>
> **The rider provisions that govern the calculation (your request #11)**
>
> Your rider [Form number] provides that the Accelerated Death Benefit equals
> the portion of the Eligible Death Benefit requested, less:
>
> * the actuarial discount (see details below);
> * an administrative charge (currently $[Amount — varies by state: $100 FL /
>   $250 elsewhere], not to exceed $500); and
> * any outstanding policy debt, if the qualifying insured is also the base
>   policy insured;
>
> and that the payment will never be less than the cash surrender value of the
> base policy, if any. A copy of the rider is available on request.
>
> **The interest rate (your request #5)**
>
> Because a future benefit is being paid early, an interest rate is used to
> express future amounts in today's dollars. The rate used for this calculation
> was **[X.XXX%]**, based on the Moody's Corporate Bond Yield Average — the
> same published index used to set the maximum policy loan interest rate on
> your policy. Under the rider, this rate may not exceed the greater of the
> yield on 90-day Treasury Bills on the election date or the maximum adjustable
> policy loan interest rate allowed by law.
>
> **How the actuarial discount is calculated**
>
> The actuarial discount is the Eligible Death Benefit less the value today —
> the present value — of the benefit being accelerated:
>
> **Actuarial Discount = Eligible Death Benefit − Value Today**
>
> The value today is built from three present-value components:
>
> * **Present Value of Future Benefits (PVFB)** — today's value of the death
>   benefit that would otherwise be paid in the future, given the modified
>   mortality table;
> * **Present Value of Future Premiums (PVFP)** — today's value of the future
>   premiums needed to keep the coverage in force to maturity; and
> * **Present Value of Future Dividends (PVFDivs)** — today's value of any
>   future dividends (zero for policies that do not pay dividends).
>
> **Value Today = PVFB − PVFP + PVFDivs**
>
> In plain terms: we start with today's value of the future death benefit,
> subtract today's value of the future premiums that would have been required
> to keep it in force, and add back today's value of any future dividends.
> From the value today we then subtract the administrative fee and any
> outstanding policy debt to arrive at the amount payable — subject to the
> cash-surrender-value minimum described above.
>
> {For this universal life policy, future premiums were determined as the level
> annual premium that keeps the policy in force to maturity, using the same
> interest rate applied elsewhere in this calculation: **$[Amount]** per year.}
>
> {For this term policy, no separate premium calculation is needed: the future
> premiums used in this calculation are the premiums already scheduled under
> the policy's premium schedule for the remainder of the term.}
>
> **Summary of this calculation (your requests #6, #7, #8, #10)**
>
> The figures behind this determination are summarized below. They show the
> key present-value components and how the accelerated benefit follows from
> them:
>
> | Description | Amount |
> |---|---|
> | Eligible Death Benefit | $[Amount] |
> | Portion requested for acceleration | 100% |
> | Death benefit being accelerated | $[Amount] |
> | Present Value of Future Benefits (PVFB) | $[Amount] |
> | Less: Present Value of Future Premiums (PVFP) | $[Amount] |
> | Plus: Present Value of Future Dividends (PVFDivs) | $[Amount] |
> | Value today of the accelerated benefit | $[Amount] |
> | Actuarial discount (amount accelerated − value today) | $[Amount] |
> | Less: Administrative Fee | $[Amount] |
> | Less: outstanding policy loan, if any | $[Amount] |
> | Calculated accelerated benefit | $[Amount] |
> | Policy's current cash surrender value | $[Amount] |
> | **Accelerated benefit payable (the greater of the two above)** | **$[Amount]** |
>
> **A note about the information in this letter (your requests #2, #3 and #10)**
>
> A few items — the individualized modified mortality table, the specific
> rating factors, and the internal medical evaluations behind them — are kept
> confidential in the claim file. We handle them this way to protect the
> insured's health information, which these documents reflect throughout, and
> because they are part of our internal underwriting and actuarial work.
> Please know this is not meant to withhold anything you need to understand
> the benefit: the summary above contains every figure used to arrive at the
> amount offered, and the actuarial methodology for this rider is on file with
> the insurance regulator as part of the approved form filing.
>
> **Additional medical information**
>
> Our goal is for the determination to reflect a complete picture of the
> insured's health. If there is additional medical information you would like
> us to consider, you are welcome to send it to us, and we will review it.
>
> **Important notices:** Depending on your circumstances, an accelerated death
> benefit may be fully or partially excludable from income under federal tax
> law (Section 101(g) of the Internal Revenue Code). Because individual
> situations vary and the exclusions are subject to limits, we recommend
> reviewing the tax treatment with a personal tax advisor before accepting the
> benefit. Receipt of an accelerated benefit may also affect eligibility for
> means-tested government programs such as Medicaid or Supplemental Security
> Income (SSI); the agency that administers the program can confirm how a
> payment would be treated. [If benefit accepted: an amended policy schedule
> page reflecting the reduced death benefit will be issued.]
>
> If you have questions about this determination or would like to discuss it
> further, please contact our office at [phone].
>
> Sincerely,
>
> [Name]
> [Title]
> cc: Agent — [Name]

---

## Part 4 — The Life-Expectancy Question (before/after)

> **DECISION (2026-08-18): life-expectancy figures are omitted from the letter
> entirely.** The app letter makes the morbidity-vs-mortality point in words
> ("a modest effect on expected mortality") without stating any LE number.
> The analysis below is retained as background in case the question is
> revisited.

**Original recommendation: share the pair — modified-table LE *and*
standard-table LE — as clearly-labeled approximations, whenever the complaint
is "I qualified, so why is the value low?"** Reasoning:

* The customer's entire confusion is *"I have a qualifying condition, why is
  there no value?"* The only honest, non-proprietary answer is "the condition
  did not materially change expected mortality," and the before/after LE pair
  is the single most intuitive way to *show* that instead of asserting it.
  One number alone ("58 years") invites the demand for the math behind it; the
  pair ("59.2 standard vs. 57.9 modified") makes the point self-evident.
* Proprietary risk is low. Two LE summary figures cannot be inverted into the
  modified table, the rating multiple, or the underwriting method. This is
  materially different from releasing the table or the monthly worksheet.
* It is consistent with what we already do: the 7/24 letter disclosed the
  projected LE; adding the standard-table comparator adds context, not new
  categories of disclosure.

**Guardrails when including it:**

1. Round to one decimal and say "approximately" — avoid false precision.
2. State explicitly that LE is a *summary output* of the mortality table, not
   an input to the calculation (prevents "recalculate my LE" from becoming a
   proxy war over the benefit).
3. Always pair it with the morbidity-vs-mortality paragraph so it reads as
   explanation, not dismissal of a condition that genuinely affects the
   insured's daily life.
4. Never accompany it with the underlying rating multiple or flat extra.
5. For *terminal* claims (short LE), get claims-management sign-off before
   putting a number in writing — telling someone their projected remaining
   lifespan is emotionally loaded and usually unnecessary there, since the
   benefit is high and the question rarely arises.

**Fallback if Legal prefers not to state figures:** use qualitative wording —
"the modified table implies a remaining life expectancy only modestly shorter
than that of a standard, healthy individual of the same age, sex and smoking
status." This preserves the teaching point without numbers.

---

## Part 5 — Gaps in the current letters (status: implemented in code 2026-08-18)

1. **Missing §6.D notices** — ✅ done; the tax and Medicaid/government-benefits
   notices are in the letter.
2. **Actuarial discount never stated as a line item** — ✅ done; explicit
   worksheet row (dollar amount only — percentage annotation removed by
   business decision).
3. **Eligible DB / portion requested rows** — ✅ done; letter always presents a
   full acceleration (100%) of the user-entered Eligible Death Benefit
   (needed for Option B policies).
4. **DOI referral** — ❌ intentionally omitted; business decision to avoid
   inviting disputes. The closing section offers only to review additional
   medical information.
5. **Rider form citation** — ✅ partially; the letter offers a copy of the rider
   on request (form number still filled per claim in manual responses).
6. **Morbidity-vs-mortality paragraph** — ✅ done; restored as the "Why
   qualifying for the benefit does not itself determine the amount" section.

Other business decisions applied to the app letter (2026-08-18):

* All life-expectancy mentions removed (figures and the word itself).
* "Pro rata" policy-debt language removed — full-acceleration assumption.
* Admin charge wording uses the state-specific fee from the quote
  ($100 FL / $250 elsewhere).
* Rider discount-factors list removed (redundant with "How the actuarial
  discount is calculated").
* Near-surrender explanatory note and worksheet percentage annotations removed.
* Neutral close — no presumption of disappointment.
