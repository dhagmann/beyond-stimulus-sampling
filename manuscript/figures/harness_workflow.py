"""Draw the manuscript's diagram of independent agents and their coordinator."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def draw():
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Tinos"],
                         "pdf.fonttype": 42, "svg.fonttype": "none"})
    fig, ax = plt.subplots(figsize=(6.5, 5.75))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.06)
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ink, line = "#23313F", "#617383"

    def box(x, y, w, h, fill="#F4F6F8", edge=line, lw=0.85):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                   boxstyle="round,pad=0.008,rounding_size=0.012",
                                   linewidth=lw, edgecolor=edge, facecolor=fill))

    def text(x, y, value, size=9, bold=False, **kwargs):
        return ax.text(x, y, value, ha="center", va="center", fontsize=size,
                       color=ink, fontweight="bold" if bold else "normal", **kwargs)

    def arrow(start, end):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                    mutation_scale=10, linewidth=0.9,
                                    color=line, shrinkA=2, shrinkB=2))

    box(0.50, 0.910, 0.86, 0.14, fill="#FFFFFF")
    text(0.50, 0.950, "Researcher", size=11, bold=True)
    text(0.50, 0.895, "Defines construct, stimulus context, construct spillover,\nand acceptance criteria", size=9.2)

    box(0.50, 0.680, 0.76, 0.215, fill="#E9EFF4", edge="#405B70", lw=1.1)
    text(0.50, 0.747, "Main coordinating agent", size=11, bold=True)
    text(0.50, 0.706, "Routes tasks and reviews returned ratings and concerns.", size=9.2)
    text(0.50, 0.665, "Applies criteria and requests targeted revisions.", size=9.2)
    text(0.50, 0.624, "Surfaces unexpected issues to the Researcher.", size=9.2)

    box(0.235, 0.330, 0.44, 0.30)
    text(0.235, 0.452, "Writer subagents", size=10.3, bold=True)
    for x, title in [(0.097, "Writer 1"), (0.235, "Writer 2"), (0.373, "…")]:
        box(x, 0.398, 0.116, 0.050, fill="#FFFFFF", lw=0.65)
        text(x, 0.398, title, size=8.9)
    text(0.235, 0.348, "Separate context for each writer", size=8.9)
    text(0.235, 0.311, "Shared inputs + assigned treatment", size=8.9)
    text(0.235, 0.239, "Different models can add variation\ne.g., ChatGPT (GPT-6.1-Sol) or Claude", size=8.8)

    box(0.765, 0.330, 0.44, 0.30)
    text(0.765, 0.452, "Judge subagents", size=10.3, bold=True)
    for x, title in [(0.680, "Judge 1"), (0.850, "Judge 2")]:
        box(x, 0.398, 0.135, 0.050, fill="#FFFFFF", lw=0.65)
        text(x, 0.398, title, size=8.9)
    text(0.765, 0.348, "Separate context for each judge", size=8.9)
    text(0.765, 0.299, "Family of stimuli with\ntreatment labels hidden", size=8.9)
    text(0.765, 0.223, "Different models can add variation\ne.g., ChatGPT (GPT-6.1-Sol) or Claude", size=8.8)

    # Straight parallel arrows leave room for labels beside the lines.
    segments = [
        ((0.30, 0.832), (0.30, 0.796)),
        ((0.70, 0.796), (0.70, 0.832)),
        ((0.16, 0.564), (0.16, 0.489)),
        ((0.35, 0.489), (0.35, 0.564)),
        ((0.65, 0.564), (0.65, 0.489)),
        ((0.84, 0.489), (0.84, 0.564)),
        ((0.50, 0.564), (0.50, 0.140)),
    ]
    for start, end in segments:
        arrow(start, end)
    labels = [
        text(0.190, 0.814, "Instructions", size=8.5),
        text(0.815, 0.814, "Unexpected issues", size=8.5),
        text(0.070, 0.526, "Generate /\nrevise", size=8.5),
        text(0.405, 0.526, "Drafts", size=8.5),
        text(0.590, 0.526, "Stimuli", size=8.5),
        text(0.930, 0.526, "Ratings /\nconcerns", size=8.5),
        text(0.620, 0.154, "Criteria met", size=8.8),
    ]
    box(0.50, 0.070, 0.88, 0.12, fill="#FFFFFF")
    text(0.50, 0.092, "Experimental stimuli and audit report", size=10.6, bold=True)
    text(0.50, 0.048, "Researcher instructions, drafts, and judge ratings saved as a report", size=9)

    # Check the issue raised in review: no arrow may run through a label.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for label in labels:
        bounds = label.get_window_extent(renderer).expanded(1.08, 1.08)
        for start, end in segments:
            p1, p2 = ax.transData.transform(start), ax.transData.transform(end)
            assert not (bounds.x0 <= p1[0] <= bounds.x1 and
                        max(min(p1[1], p2[1]), bounds.y0) <= min(max(p1[1], p2[1]), bounds.y1)), label.get_text()

    folder = Path(__file__).resolve().parent
    for extension in ["pdf", "svg", "png"]:
        fig.savefig(folder / f"harness_workflow.{extension}", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    draw()
