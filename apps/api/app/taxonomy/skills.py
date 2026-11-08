"""Curated skills taxonomy.

Phase 1 ships a compact, auditable alias table instead of bundling ESCO/O*NET
(which are large, licensed differently, and better loaded in Phase 2). The
interface here is intentionally the same shape a taxonomy loader would expose:
canonical name, aliases, category, and ambiguity flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    canonical: str
    aliases: tuple[str, ...]
    category: str = "general"
    # Short/ordinary-word aliases that need capitalisation or context to match.
    ambiguous: bool = False

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


def _skill(canonical: str, *aliases: str, category: str = "general", ambiguous: bool = False) -> Skill:
    return Skill(canonical=canonical, aliases=aliases, category=category, ambiguous=ambiguous)


SKILLS: tuple[Skill, ...] = (
    # Languages
    _skill("Python", "python3", "py", category="language", ambiguous=True),
    _skill("JavaScript", "js", "ecmascript", category="language"),
    _skill("TypeScript", "ts", category="language"),
    _skill("Java", category="language", ambiguous=True),
    _skill("C#", "csharp", "c sharp", category="language"),
    _skill("C++", "cpp", "c plus plus", category="language"),
    _skill("Go", "golang", category="language", ambiguous=True),
    _skill("Rust", category="language"),
    _skill("Ruby", category="language"),
    _skill("PHP", category="language"),
    _skill("Swift", category="language"),
    _skill("Kotlin", category="language"),
    _skill("Scala", category="language"),
    _skill("R", category="language", ambiguous=True),
    _skill("SQL", category="language"),
    _skill("Bash", "shell scripting", "shell", category="language"),
    _skill("HTML", "html5", category="language"),
    _skill("CSS", "css3", category="language"),
    _skill("LaTeX", "tex", category="language"),
    # Backend / frameworks
    _skill("FastAPI", "fast api", category="backend"),
    _skill("Django", category="backend"),
    _skill("Flask", category="backend"),
    _skill("Node.js", "nodejs", "node", category="backend"),
    _skill("Express", "express.js", "expressjs", category="backend"),
    _skill("NestJS", "nest.js", "nestjs", category="backend"),
    _skill("Spring Boot", "springboot", "spring", category="backend"),
    _skill(".NET", "dotnet", "asp.net", "aspnet", category="backend"),
    _skill("Ruby on Rails", "rails", "ror", category="backend"),
    _skill("GraphQL", "graph ql", category="backend"),
    _skill("gRPC", "grpc", category="backend"),
    _skill("REST", "rest api", "restful", category="backend"),
    _skill("WebSockets", "websocket", "socket.io", category="backend"),
    # Frontend
    _skill("React", "react.js", "reactjs", category="frontend"),
    _skill("Next.js", "nextjs", "next js", category="frontend"),
    _skill("Vue", "vue.js", "vuejs", category="frontend"),
    _skill("Angular", "angularjs", category="frontend"),
    _skill("Svelte", "sveltekit", category="frontend"),
    _skill("Tailwind CSS", "tailwind", "tailwindcss", category="frontend"),
    _skill("Redux", category="frontend"),
    _skill("Vite", category="frontend"),
    _skill("Webpack", category="frontend"),
    # Data
    _skill("PostgreSQL", "postgres", "psql", category="data"),
    _skill("MySQL", category="data"),
    _skill("SQLite", category="data"),
    _skill("MongoDB", "mongo", category="data"),
    _skill("Redis", category="data"),
    _skill("Elasticsearch", "elastic search", category="data"),
    _skill("Kafka", "apache kafka", category="data"),
    _skill("RabbitMQ", "rabbit mq", category="data"),
    _skill("Snowflake", category="data"),
    _skill("BigQuery", "big query", category="data"),
    _skill("Spark", "apache spark", "pyspark", category="data"),
    _skill("Airflow", "apache airflow", category="data"),
    _skill("dbt", category="data"),
    _skill("Pandas", category="data"),
    _skill("NumPy", "numpy", category="data"),
    # Cloud / infra / devops
    _skill("AWS", "amazon web services", category="cloud"),
    _skill("GCP", "google cloud", "google cloud platform", category="cloud"),
    _skill("Azure", "microsoft azure", category="cloud"),
    _skill("Docker", "containerization", category="devops"),
    _skill("Kubernetes", "k8s", category="devops"),
    _skill("Terraform", category="devops"),
    _skill("Ansible", category="devops"),
    _skill("Helm", category="devops"),
    _skill("Jenkins", category="devops"),
    _skill("GitHub Actions", "github action", category="devops"),
    _skill("GitLab CI", "gitlab", category="devops"),
    _skill("CI/CD", "ci cd", "continuous integration", "continuous delivery", category="devops"),
    _skill("Linux", "unix", category="devops"),
    _skill("Nginx", "nginx", category="devops"),
    _skill("Serverless", "lambda", category="cloud"),
    _skill("Observability", "monitoring", "opentelemetry", category="devops"),
    _skill("Prometheus", category="devops"),
    _skill("Grafana", category="devops"),
    # ML / AI
    _skill("Machine Learning", "ml", category="ml"),
    _skill("Deep Learning", "dl", category="ml"),
    _skill("PyTorch", "pytorch", category="ml"),
    _skill("TensorFlow", "tensorflow", category="ml"),
    _skill("scikit-learn", "sklearn", "scikit learn", category="ml"),
    _skill("NLP", "natural language processing", category="ml"),
    _skill("Computer Vision", "cv", category="ml"),
    _skill("LLM", "large language model", "large language models", category="ml"),
    _skill("RAG", "retrieval augmented generation", category="ml"),
    _skill("LangChain", "langchain", category="ml"),
    _skill("LangGraph", "langgraph", category="ml"),
    _skill("pgvector", category="ml"),
    _skill("Embeddings", "embedding", category="ml"),
    _skill("MLOps", "ml ops", category="ml"),
    # Testing / quality
    _skill("pytest", category="testing"),
    _skill("Jest", category="testing"),
    _skill("Playwright", category="testing"),
    _skill("Cypress", category="testing"),
    _skill("Selenium", category="testing"),
    _skill("Unit Testing", "unit tests", "unit test", category="testing"),
    _skill("TDD", "test driven development", category="testing"),
    # Product / design / process
    _skill("Agile", "scrum", "kanban", category="process"),
    _skill("Jira", category="process"),
    _skill("Figma", category="design"),
    _skill("Git", "version control", category="process"),
    _skill("System Design", "distributed systems", category="architecture"),
    _skill("Microservices", "micro services", category="architecture"),
    _skill("API Design", "api development", category="architecture"),
    _skill("Data Modeling", "data modelling", "schema design", category="architecture"),
    _skill("Security", "application security", "appsec", category="security"),
    _skill("OAuth", "oauth2", "oauth 2", category="security"),
    _skill("JWT", "json web token", category="security"),
    # Soft / leadership
    _skill("Leadership", "team lead", "led a team", category="soft"),
    _skill("Mentoring", "mentorship", "mentored", category="soft"),
    _skill("Stakeholder Management", "stakeholders", category="soft"),
    _skill("Communication", "written communication", category="soft"),
    _skill("Problem Solving", "problem-solving", category="soft"),
    _skill("Collaboration", "cross-functional", "cross functional", category="soft"),
)

_ALIAS_INDEX: dict[str, Skill] = {}
for _entry in SKILLS:
    for _name in _entry.all_names:
        _ALIAS_INDEX.setdefault(_name.lower(), _entry)

# Longest alias first so "machine learning" wins over "ml"-style fragments.
_ORDERED_ALIASES: list[tuple[str, Skill]] = sorted(
    _ALIAS_INDEX.items(), key=lambda item: len(item[0]), reverse=True
)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


_COMPILED: list[tuple[re.Pattern[str], Skill, str]] = [
    (_alias_pattern(alias), skill, alias) for alias, skill in _ORDERED_ALIASES
]


@dataclass
class SkillMatch:
    canonical: str
    matched_text: str
    alias: str
    category: str
    start: int
    end: int
    exact: bool
    ambiguous: bool = field(default=False)


def _looks_like_acronym_context(text: str, start: int, end: int) -> bool:
    """Ambiguous aliases (Go, R, JS, ...) need caps or a nearby skill cue."""

    span = text[start:end]
    if span[:1].isupper():
        return True
    window = text[max(0, start - 40) : min(len(text), end + 40)].lower()
    cues = (
        "experience with",
        "proficient in",
        "knowledge of",
        "familiar with",
        "skills",
        "using",
        "written in",
        "developer",
        "engineer",
    )
    return any(cue in window for cue in cues)


def find_skills(text: str) -> list[SkillMatch]:
    """Return non-overlapping canonical skill matches, longest alias first."""

    matches: list[SkillMatch] = []
    taken: list[tuple[int, int]] = []
    for pattern, skill, alias in _COMPILED:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            if skill.ambiguous and not _looks_like_acronym_context(text, start, end):
                continue
            # "Go" should not match the verb "go".
            if skill.canonical == "Go" and text[start:end].islower():
                continue
            if skill.canonical == "R" and text[start:end].islower():
                continue
            if (
                skill.canonical == "Java"
                and text[start:end].lower() == "java"
                and text[max(0, start - 8) : start].lower().strip().endswith("script")
            ):
                continue
            taken.append((start, end))
            matches.append(
                SkillMatch(
                    canonical=skill.canonical,
                    matched_text=match.group(0),
                    alias=alias,
                    category=skill.category,
                    start=start,
                    end=end,
                    exact=match.group(0).lower() == skill.canonical.lower(),
                    ambiguous=skill.ambiguous,
                )
            )
    matches.sort(key=lambda item: item.start)
    return matches


def canonical_for(value: str) -> str | None:
    entry = _ALIAS_INDEX.get(value.strip().lower())
    return entry.canonical if entry else None


def category_for(canonical: str) -> str:
    for skill in SKILLS:
        if skill.canonical == canonical:
            return skill.category
    return "general"


def canonical_skills() -> list[str]:
    return [skill.canonical for skill in SKILLS]
