from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scoring.repository import (  # noqa: E402
    build_catalog,
    finalization_statistics,
    save_finalization,
)


# Exact, reviewed editorial changes. Keeping the expected original text makes
# the migration refuse to overwrite a later human edit.
CHANGES = {
    "res_e58db18175a00b67765ffe8d": (
        "Верно разобран случай B = 1 и компактно описана первая грамматика.\n\n"
        "В случае B = 3 подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
        "Верно разобран случай $B=1$ и компактно описана первая грамматика.\n\n"
        "В случае $B=3$ подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
    ),
    "res_e622be056707772e4d657d07": (
        "Верно разобран случай N_b = 5 и компактно описана первая грамматика.\n\n"
        "В случае N_b = 15 подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
        "Верно разобран случай $N_b=5$ и компактно описана первая грамматика.\n\n"
        "В случае $N_b=15$ подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
    ),
    "res_28e4a6c14917e34775d9a741": (
        'В части "2. Анализ грамматики " неверно утверждается, что все слова G_2 имеют чётную длину. Это ломает все последующие рассуждения.',
        'В части «2. Анализ грамматики» неверно утверждается, что все слова $G_2$ имеют чётную длину. Это ломает все последующие рассуждения.',
    ),
    "res_dfb0af1430f31ccc46e03c5a": (
        "Верно разобран случай m = 1 и компактно описана первая грамматика.\n\n"
        "В случае m = 3 подсчитано число деревьев вывода (причём с ошибкой), что не совпадает с числом слов, поскольку грамматика неоднозначна.",
        "Верно разобран случай $m=1$ и компактно описана первая грамматика.\n\n"
        "В случае $m=3$ подсчитано число деревьев вывода (причём с ошибкой), что не совпадает с числом слов, поскольку грамматика неоднозначна.",
    ),
    "res_891a1740598d690d052d5b7b": (
        "Вывод части «2. Анализ грамматики  G_2» неверен: между соседними буквами b может быть любое чётное ненулевое количество букв a, а не только 2. Это ломает все дальнейшие рассуждения.",
        "Вывод части «2. Анализ грамматики $G_2$» неверен: между соседними буквами $b$ может быть любое чётное ненулевое количество букв $a$, а не только $2$. Это ломает все дальнейшие рассуждения.",
    ),
    "res_cde0495f6f17a77fa8fe554b": (
        "Полное отсуствие объяснения откуда взялось C(44, 4) было принято считать достаточно важным, чтоб не начислять за это баллы",
        "Полное отсутствие объяснения, откуда взялось $\\binom{44}{4}$, было принято считать достаточно важным, чтобы не начислять за это баллы.",
    ),
    "res_aed2d270cb788986b5a9f08e": (
        "Шаг 2 содержит ошибку в выводе: количество букв b кратно 5, а не 4. Это ломает все последующие рассуждения.",
        "Шаг 2 содержит ошибку в выводе: количество букв $b$ кратно $5$, а не $4$. Это ломает все последующие рассуждения.",
    ),
    "res_df422c9c6d1e9feccc8d7126": (
        "Верно разобран случай с 5 буквами b(n = 1) и компактно описана G_1.\n\n"
        "В случае с 15 буквами b(n = 3) подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
        "Верно разобран случай с $5$ буквами $b$ ($n=1$) и компактно описана $G_1$.\n\n"
        "В случае с $15$ буквами $b$ ($n=3$) подсчитано число деревьев вывода, что не совпадает с числом слов, поскольку грамматика неоднозначна.",
    ),
    "res_921c7927cf2004913bf3516c": (
        "В решении используется равенство T² = T, которое неверно.",
        "В решении используется равенство $T^2=T$, которое неверно.",
    ),
    "res_b407d351135c5348c037f63a": (
        "В доказательстве неверно используется свойство проектора AB + BA. Для u = (AB + BA)v не будет выполнено (AB+BA)u = Tv.",
        "В доказательстве неверно используется свойство проектора $AB+BA$. Для $u=(AB+BA)v$ не будет выполнено $(AB+BA)u=Tv$.",
    ),
    "res_200e49dad5fab549e1e88d0c": (
        "В формуле 2P(m)-P(m+1) есть неточности, но они не влияют на суть решения",
        "В формуле $2P(m)-P(m+1)$ есть неточности, но они не влияют на суть решения.",
    ),
    "res_6e01e0421686e0a83a60e50a": (
        "Утверждение, что все коэффициенты должны быть целыми, неверно. Например для многочлена x(x+1)/2, который принимает целые значения во всех целых точках, поэтому четвёртый шаг и итоговый вывод не работают.",
        "Утверждение, что все коэффициенты должны быть целыми, неверно. Например, многочлен $\\frac{x(x+1)}{2}$ принимает целые значения во всех целых точках, поэтому четвёртый шаг и итоговый вывод не работают.",
    ),
    "res_9c21371ad3fd726abd42a2eb": (
        "Заявлено, что в графе без изолированных вершин есть паросочетание, насыщающее почти все вершины, но это неверно. Поэтому верхняя оценка 3/7 не доказана.",
        "Заявлено, что в графе без изолированных вершин есть паросочетание, насыщающее почти все вершины, но это неверно. Поэтому верхняя оценка $\\frac{3}{7}$ не доказана.",
    ),
    "res_e45527543abc6fd7630128b8": (
        "Ошибка в оценке: из δ(G[S]) ≥ 1 следует только E(S) = 1/2 * Σ_{v∈S} d_S(v) ≥ |S|/2, а не E(S) ≥ |S|. Поэтому вывод |M| ≤ n²/3 не обоснован.",
        "Ошибка в оценке: из $\\delta(G[S])\\ge 1$ следует только $E(S)=\\frac12\\sum_{v\\in S}d_S(v)\\ge\\frac{|S|}{2}$, а не $E(S)\\ge |S|$. Поэтому вывод $|M|\\le\\frac{n^2}{3}$ не обоснован.",
    ),
    "res_1de474e83df1c73221f7be51": (
        'При устной проверке r_n = q_n + 1, "достаточно долго, чтоб среднее" и разрыва производной залатываются',
        'При устной проверке $r_n=q_n+1$, «достаточно долго, чтобы среднее» и разрыв производной уточняются.',
    ),
    "res_42ed0e74e637c4aaec4ace13": (
        'Ключевое утверждение: прямые AX_A, BX_B, CX_C  не являются попарными радосями w_A, w_B, w_C неверно.\n\n'
        'Основные ошибки в рассуждениях:\n\n'
        'Вместо "Нужный знак (точки пересечения внутри \\Omega_A) даёт u=c+d, v=b+d" должно быть "u=b, v=c"\n\n'
        'После инверсии рад-ось окружностей не переходит в рад-ось.',
        'Ключевое утверждение «прямые $AX_A$, $BX_B$, $CX_C$ не являются попарными радикальными осями $\\omega_A$, $\\omega_B$, $\\omega_C$» неверно.\n\n'
        'Основные ошибки в рассуждениях:\n\n'
        'Вместо «Нужный знак (точки пересечения внутри $\\Omega_A$) даёт $u=c+d$, $v=b+d$» должно быть «$u=b$, $v=c$».\n\n'
        'После инверсии радикальная ось окружностей не переходит в радикальную ось.',
    ),
    "res_e821e6ac56ce527d5c8a5356": (
        'Решение неверно. Основные ошибки:\n\n'
        '1) Подмена понятий (шаг 2). Окружность подобия — это ГМТ точек, для которых $\\frac{|PQ_B|}{|PQ_C|}=\\frac{R_B}{R_C}$ (отношение расстояний до центров). А в скобках решение определяет совсем другое ГМТ: через отношение касательных, то есть $\\frac{\\mathrm{pow}{\\Omega_B}(P)}{\\mathrm{pow}{\\Omega_C}(P)}=\\frac{R_B}{R_C}$. Это разные окружности.\n\n'
        '2)"AX_A​ — радось ω и S_A​" неверно(шаг 3)\n\n'
        '3) Касания $\\Omega_A$ с $\\omega_B,\\omega_C$ не используются нигде',
        'Решение неверно. Основные ошибки:\n\n'
        '1. Подмена понятий (шаг 2). Окружность подобия — это ГМТ точек, для которых $\\frac{|PQ_B|}{|PQ_C|}=\\frac{R_B}{R_C}$ (отношение расстояний до центров). В скобках решение определяет другое ГМТ — через отношение касательных: $\\frac{\\operatorname{pow}_{\\Omega_B}(P)}{\\operatorname{pow}_{\\Omega_C}(P)}=\\frac{R_B}{R_C}$. Это разные окружности.\n\n'
        '2. Утверждение «$AX_A$ — радикальная ось $\\omega$ и $S_A$» неверно (шаг 3).\n\n'
        '3. Касания $\\Omega_A$ с $\\omega_B,\\omega_C$ не используются нигде.',
    ),
    "res_def35046089a640988a23559": (
        "В шаге 3 допущено неверное сокращение на ab, из-за чего заключение шагов 4 и 5 неверно: существуют конструкции с попарно различными радиусами и длинами сторон треугольника.",
        "В шаге 3 допущено неверное сокращение на $ab$, из-за чего заключение шагов 4 и 5 неверно: существуют конструкции с попарно различными радиусами и длинами сторон треугольника.",
    ),
}


def normalized(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Format math in approved final comments as LaTeX.")
    parser.add_argument("--competitions-dir", type=Path, default=Path("data/competitions"))
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--results-dir", type=Path, default=Path("data/results"))
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = build_catalog(
        competitions_dir=args.competitions_dir,
        logs_dir=args.logs_dir,
        results_dir=args.results_dir,
    )
    found: dict[str, tuple[str, dict, dict, dict]] = {}
    for competition_id in ("math-cup-2026-qualifying", "math-cup-2026-final"):
        competition = catalog["competition_map"][competition_id]
        for row in finalization_statistics(competition)["tasks"]:
            for cell in row["cells"].values():
                attempt = cell["attempt"]
                final = attempt.get("finalization") if attempt else None
                result_id = str(attempt.get("result_id") or "") if attempt else ""
                if result_id in CHANGES and final:
                    found[result_id] = (competition_id, row["problem"], attempt, final)

    missing = sorted(set(CHANGES) - set(found))
    if missing:
        raise SystemExit(f"Missing selected finalizations: {', '.join(missing)}")

    pending = []
    for result_id, (before, after) in CHANGES.items():
        competition_id, problem, attempt, final = found[result_id]
        if final.get("feedback_review_required"):
            raise SystemExit(f"Final comment is not approved: {result_id}")
        current = normalized(str(final.get("feedback") or ""))
        if current == normalized(after):
            continue
        if current != normalized(before):
            raise SystemExit(f"Final comment changed unexpectedly: {result_id}")
        pending.append((competition_id, problem, attempt, final, after))

    print(f"Would format math in {len(pending)} approved final comments.")
    if not args.apply:
        return 0
    for competition_id, problem, attempt, final, feedback in pending:
        save_finalization(
            results_dir=args.results_dir,
            competition_id=competition_id,
            problem_id=problem["problem_id"],
            run_id=attempt["run_id"],
            result_id=attempt["result_id"],
            result_index=int(attempt["result_index"]),
            model_key_value=attempt["model_key"],
            model=attempt["model_id"],
            score=final["score"],
            max_score=float(problem["max_score"]),
            feedback=feedback,
            updated_by="latex-formatting",
            feedback_review_required=False,
        )
    print(f"Formatted math in {len(pending)} approved final comments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
