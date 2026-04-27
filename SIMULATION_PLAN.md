# BC4D Intel — Pipeline Simulation Plan

## Purpose
Test the pipeline LOGIC against synthetic datasets. The goal is NOT to optimize for these specific test cases (that would be overfitting) but to verify the ARCHITECTURE makes sound decisions about:
- When to use the cache vs when to call AI
- Whether the 6-layer safety catches real problems
- Whether the taxonomy design produces usable categories
- Whether the cross-encoder classification is precise enough
- Where the pipeline breaks and needs structural improvement

## What the User Should Prepare

Place these files in `C:/Users/beyer/Claude/V2/BC4D Intel/`:

1. **`test_positive.xlsx`** — Synthetic post-survey with clearly positive responses
   - Responses that should be easy to classify (praise, clear feedback)
   - Tests: does the cache match common positive patterns?

2. **`test_negative.xlsx`** — Synthetic post-survey with clearly negative responses
   - Criticism, complaints, suggestions for improvement
   - Tests: does the safety system prevent matching negatives to positive cache entries?

3. **`test_mixed.xlsx`** — Realistic mix of positive, negative, ambiguous, off-topic
   - Tests: does the pipeline make reasonable split between cache hits and AI calls?

4. **`test_edge.xlsx`** (optional) — Edge cases: very short, sarcastic, off-topic, multilingual
   - Tests: does the safety system catch tricky cases?

Each file should have columns matching the post-survey format:
- Pseudokey columns (any text)
- Free-text columns with headers similar to real questions

## Simulation Phases

### Phase 1: Cache Hit Rate Test (no API cost)
For each test file, run the cache matching WITHOUT calling AI.
Measure: what % would be cache hits vs misses?
Expected: positive file ~70-80% hits, negative file ~20-30% hits (safety blocks), mixed ~50-60%.

### Phase 2: Safety Guard Audit
Feed known tricky pairs through the 6-layer safety system:
- Positive response on "Verbesserung" question → should MISS
- Negative response on "Staerken" question → should MISS
- Negated version of common answer → should MISS
- Very short ambiguous response → should MISS (short-text guard)
- Same-sentiment paraphrase → should HIT

### Phase 3: Full Pipeline Run (costs ~$0.10-0.30)
Run the complete pipeline on the mixed test file:
1. Cache check → some cached, some uncached
2. AI taxonomy for uncached → verify categories make sense
3. Cross-encoder classify → check confidence distribution
4. Edge case review → verify AI improves low-confidence assignments

### Phase 4: Classification Quality Audit
For each response in the test files, manually verify:
- Is the assigned category correct?
- If from cache: was the match appropriate?
- If from AI: is the taxonomy category reasonable?
Calculate: accuracy, precision, recall per category.

### Phase 5: Architecture Decisions
Based on Phases 1-4, answer:
1. Is the 0.78 threshold right? (too high = too many AI calls, too low = mismatches)
2. Are the 6 safety layers necessary? (any layer that never triggers = remove)
3. Is the cache size sufficient? (4,387 entries — enough coverage?)
4. Does the pipeline make the RIGHT decision about cache vs AI?
5. Are there failure patterns that suggest a structural change?

## How to Run

```bash
cd "C:/Users/beyer/Claude/V2/BC4D Intel"

# Phase 1: Quick cache test (no API cost)
python -c "
from bc4d_intel.core.answer_cache import classify_from_cache
import pandas as pd

# Load test file
df = pd.read_excel('test_mixed.xlsx')
# Find free-text columns and test each
for col in df.columns:
    responses = df[col].dropna().astype(str).tolist()
    responses = [r for r in responses if len(r.strip()) > 3]
    if len(responses) < 5: continue

    cached, uncached = classify_from_cache(f'[Post] {col}', responses)
    hit_rate = len(cached) / (len(cached) + len(uncached)) * 100
    print(f'{col[:40]}: {hit_rate:.0f}% cache hits ({len(cached)}/{len(cached)+len(uncached)})')
"

# Phase 3: Full pipeline (costs money)
python -c "
from bc4d_intel.core.embedder import full_pipeline
from bc4d_intel.app_state import AppState
import pandas as pd

state = AppState.load()
df = pd.read_excel('test_mixed.xlsx')
# ... run full_pipeline on each free-text column
"
```

## Key Metrics to Track

| Metric | Target | Red Flag |
|--------|--------|----------|
| Cache hit rate (positive) | >70% | <50% |
| Cache hit rate (negative) | <30% | >50% (safety failure) |
| Cache hit rate (mixed) | 50-60% | <30% or >80% |
| False positives (wrong cache match) | <5% | >10% |
| Safety blocks (correct) | >90% of blocks justified | <70% |
| Taxonomy quality | >80% categories meaningful | <60% |
| Classification accuracy | >85% | <70% |
| Cost per staffel (with cache) | <$0.30 | >$0.50 |

## What NOT to Do

- Do NOT adjust the threshold to match specific test data
- Do NOT add test responses to the cache (that's cheating)
- Do NOT modify the safety rules to pass specific cases
- DO look for PATTERNS of failure that suggest architectural changes
- DO consider if the 6 layers are the right abstraction
- DO consider if cross-encoder is the right matching tool
