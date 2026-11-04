"""Load stages, lessons, quizzes and exercises from datalab/curriculum.

Stage file (curriculum/stages/NN-name.md)::

    id: clean
    title: Clean
    summary: one line
    --- lesson
    markdown ...
    --- quiz
    Q: question text
    - wrong answer
    * right answer
    E: explanation shown after answering

Exercise file (curriculum/exercises/*.ex)::

    id: clean-py-1
    stage: clean
    lang: python            # sql | python | r
    title: ...
    level: 1                # 1 core, 2 stretch
    ordered: false          # SQL only: does row order matter?
    needs: shap             # optional extra packages, comma separated
    --- task
    markdown
    --- starter
    --- solution
    --- check               # Python/R code; SQL exercises compare to the solution
    --- hints               # one hint per line starting with "- "
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent / "curriculum"
LANGS = ("sql", "python", "r")
SECTION = re.compile(r"^--- ?([a-z]+)\s*$")


def _split(text: str) -> tuple[dict, dict]:
    head: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    cur = None
    for line in text.replace("\r\n", "\n").split("\n"):
        m = SECTION.match(line)
        if m:
            cur = m.group(1)
            sections[cur] = []
            continue
        if cur is None:
            if line.strip() and ":" in line:
                k, v = line.split(":", 1)
                head[k.strip()] = v.strip()
        else:
            sections[cur].append(line)
    return head, {k: "\n".join(v).strip("\n") + ("\n" if k in ("starter", "solution", "check") else "")
                  for k, v in sections.items()}


@dataclass
class Question:
    text: str
    options: list[str]
    answer: int
    explain: str = ""


@dataclass
class Stage:
    id: str
    order: int
    title: str
    summary: str
    lesson: str
    quiz: list[Question] = field(default_factory=list)


@dataclass
class Exercise:
    id: str
    stage: str
    lang: str
    title: str
    task: str
    starter: str
    solution: str
    check: str = ""
    hints: list[str] = field(default_factory=list)
    level: int = 1
    ordered: bool = False
    needs: list[str] = field(default_factory=list)
    order: int = 0

    def public(self) -> dict:
        return {"id": self.id, "stage": self.stage, "lang": self.lang, "title": self.title,
                "task": self.task, "starter": self.starter, "hints": self.hints, "level": self.level,
                "needs": self.needs, "ordered": self.ordered}

    def summary(self) -> dict:
        return {"id": self.id, "stage": self.stage, "lang": self.lang, "title": self.title,
                "level": self.level, "needs": self.needs}


def _parse_quiz(text: str) -> list[Question]:
    qs: list[Question] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Q:"):
            qs.append(Question(s[2:].strip(), [], -1))
        elif qs and s.startswith(("- ", "* ")):
            if s.startswith("* "):
                qs[-1].answer = len(qs[-1].options)
            qs[-1].options.append(s[2:].strip())
        elif qs and s.startswith("E:"):
            qs[-1].explain = s[2:].strip()
    return qs


def load_stages(root: Path = HERE) -> list[Stage]:
    out = []
    for f in sorted((root / "stages").glob("*.md")):
        head, sec = _split(f.read_text(encoding="utf-8"))
        out.append(Stage(head["id"], int(f.name.split("-")[0]), head["title"], head.get("summary", ""),
                         sec.get("lesson", ""), _parse_quiz(sec.get("quiz", ""))))
    return out


def load_exercises(root: Path = HERE) -> list[Exercise]:
    out = []
    for i, f in enumerate(sorted((root / "exercises").glob("*.ex"))):
        head, sec = _split(f.read_text(encoding="utf-8"))
        hints = [h.strip()[2:].strip() for h in sec.get("hints", "").splitlines() if h.strip().startswith("- ")]
        ex = Exercise(
            id=head["id"], stage=head["stage"], lang=head["lang"], title=head["title"],
            task=sec.get("task", ""), starter=sec.get("starter", ""), solution=sec.get("solution", ""),
            check=sec.get("check", "").strip() and sec.get("check", ""), hints=hints,
            level=int(head.get("level", 1)), ordered=head.get("ordered", "false").lower() == "true",
            needs=[n.strip() for n in head.get("needs", "").split(",") if n.strip()], order=i,
        )
        if ex.lang not in LANGS:
            raise ValueError(f"{f.name}: unknown lang {ex.lang}")
        out.append(ex)
    return out


class Curriculum:
    def __init__(self, root: Path = HERE):
        self.stages = load_stages(root)
        self.exercises = load_exercises(root)
        self.by_id = {e.id: e for e in self.exercises}
        stage_ids = {s.id for s in self.stages}
        for e in self.exercises:
            if e.stage not in stage_ids:
                raise ValueError(f"exercise {e.id}: unknown stage {e.stage}")
        lang_rank = {l: i for i, l in enumerate(LANGS)}
        stage_rank = {s.id: s.order for s in self.stages}
        self.exercises.sort(key=lambda e: (stage_rank[e.stage], e.level, lang_rank[e.lang], e.order))

    def stage(self, sid: str) -> Stage | None:
        return next((s for s in self.stages if s.id == sid), None)
