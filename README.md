# Code Review Academy - Python4LLM

This repository is a **hands-on lab for mastering code reviews**, specializing in Python for LLMs, following industry-leading practices. Each exercise presents a version of code full of issues (`bad/`) and a refined version (`good/`).
Instead of merging into `main`, each exercise lives in its own pair of branches—`exercise-NN-bad` and `exercise-NN-good`—so that you review the diff.

---

## 📚 Repo Structure & Review PRs

**Main branch** (`main`)
   - Only contains guiding documentation and doesn’t hold exercise code.
   - Housekeeping for shared resources: style guides, checklists, templates.

Each exercise has:

- A **bad branch** (`exercise-NN-bad`) with the intentionally flawed code.
- A **good branch** (`exercise-NN-good`) with the refactored solution.
- A **Draft Pull Request (good → bad)** that shows the exact diff and preserves inline review comments.

This way, you can:
- Browse the bad and good code directly.
- Open the Draft PR to study the changes and review notes.
- Practice leaving your own comments in your fork.


### 🔎 Exercise Index (WIP)

#### Exercise 01 – Fetch Weather
- **Bad branch:** [`exercise-01-bad`](../../tree/exercise-01-bad)
- **Good branch:** [`exercise-01-good`](../../tree/exercise-01-good)
- **Draft PR (diff + comments):** [#1](../../pull/1)

*(Add more as exercises grow.)*

---

### 🧭 How to Practice Yourself

1. **Fork this repo**.  
2. Create branches in your fork using the bad/good files from `exercises/NN-topic/`.  
3. Open a PR (`good → bad`) in your **own fork**, mark it as **Draft**, and do your review inline.  
4. Compare your notes with the `good/` solution in `main`.  
5. Optionally, share your PR link in Discussions for peer feedback.


### 📝 Review Checklist

When leaving comments, structure your feedback as:

- **Blockers**: correctness, security, reliability issues (must fix).  
- **Important**: maintainability, performance, observability (should fix).  
- **Nice-to-have**: readability, polish, style (optional).

---

## 🤝 Contributing

Contributions are welcome. Add new exercises (`exercise-NN-bad` / `exercise-NN-good`)  
or improve existing ones by submitting pull requests.

---

## 📜 License

MIT License.  
Use freely for practice, workshops, or teaching.