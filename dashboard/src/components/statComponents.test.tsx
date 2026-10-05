import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { STATS_WINDOWS } from "../lib/windows";
import { statsFixture } from "../test/statsServer";
import { DeliveryCard } from "./DeliveryCard";
import { OutcomeTable } from "./OutcomeTable";
import { StatCard } from "./StatCard";
import { WindowSelect } from "./WindowSelect";

describe("StatCard", () => {
  it("is a region named after its title", () => {
    render(<StatCard title="Cost" value="$0.0022" />);
    const card = screen.getByRole("article", { name: "Cost" });
    expect(within(card).getByText("$0.0022")).toBeInTheDocument();
  });

  it("shows a hint when there is one", () => {
    render(<StatCard title="Cost" value="$1" hint="per 1,000 requests" />);
    expect(screen.getByText("per 1,000 requests")).toBeInTheDocument();
  });

  it("folds longer details away behind a summary", () => {
    render(<StatCard title="Agreement" value="50%" details="The long explanation." />);
    expect(screen.getByText("What does this mean?")).toBeInTheDocument();
    expect(screen.getByText("The long explanation.")).toBeInTheDocument();
  });

  it("has no summary without details", () => {
    render(<StatCard title="Cost" value="$1" />);
    expect(screen.queryByText("What does this mean?")).not.toBeInTheDocument();
  });

  it("can be marked as a warning", () => {
    const { container } = render(<StatCard title="Failed" value="3" tone="warning" />);
    expect(container.querySelector("article")?.className).toMatch(/warning/);
  });
});

describe("WindowSelect", () => {
  it("offers the three windows as one group of radio buttons", () => {
    render(<WindowSelect options={STATS_WINDOWS} value="24h" onChange={() => {}} />);
    expect(screen.getByRole("group", { name: "Time window" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    for (const name of ["Last 24 hours", "Last 7 days", "All time"]) {
      expect(screen.getByRole("radio", { name })).toBeInTheDocument();
    }
  });

  it("marks the current window", () => {
    render(<WindowSelect options={STATS_WINDOWS} value="7d" onChange={() => {}} />);
    expect(screen.getByRole("radio", { name: "Last 7 days" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Last 24 hours" })).not.toBeChecked();
  });

  it("reports the window that was chosen", async () => {
    const onChange = vi.fn();
    render(<WindowSelect options={STATS_WINDOWS} value="24h" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "All time" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("all");
  });

  it("does not report a click on the window that is already chosen", async () => {
    const onChange = vi.fn();
    render(<WindowSelect options={STATS_WINDOWS} value="24h" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Last 24 hours" }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("moves with the arrow keys", async () => {
    const onChange = vi.fn();
    render(<WindowSelect options={STATS_WINDOWS} value="24h" onChange={onChange} />);
    screen.getByRole("radio", { name: "Last 24 hours" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("7d");
  });
});

describe("OutcomeTable", () => {
  it("lists where the requests ended, with counts and shares", () => {
    render(<OutcomeTable stats={statsFixture()} />);
    const rows = screen.getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual([
      "Accepted by baseline9648.0%",
      "Accepted by llm10251.0%",
      "Sent to a person21.0%",
    ]);
  });

  it("sorts the tiers by name, whatever order the API used", () => {
    render(<OutcomeTable stats={statsFixture({ accepted_by_tier: { llm: 1, baseline: 1 }, requests: 3, human_review: 1 })} />);
    const names = screen.getAllByRole("rowheader").map((cell) => cell.textContent);
    expect(names).toEqual(["Accepted by baseline", "Accepted by llm", "Sent to a person"]);
  });

  it("copes with a tier that accepted nothing at all", () => {
    render(<OutcomeTable stats={statsFixture({ accepted_by_tier: { baseline: 5 }, requests: 5, human_review: 0 })} />);
    expect(screen.getByText("Sent to a person").closest("tr")).toHaveTextContent("00.0%");
  });

  it("says so when the window has no requests, instead of a table of zeros", () => {
    render(<OutcomeTable stats={statsFixture({ requests: 0, accepted_by_tier: {}, human_review: 0 })} />);
    expect(screen.getByText("No requests in this window.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("separates thousands", () => {
    render(<OutcomeTable stats={statsFixture({ requests: 12000, accepted_by_tier: { baseline: 11000 }, human_review: 1000 })} />);
    expect(screen.getByText("11,000")).toBeInTheDocument();
  });

  it("has proper table headers", () => {
    render(<OutcomeTable stats={statsFixture()} />);
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Outcome", "Requests", "Share"]);
  });
});

describe("DeliveryCard", () => {
  const delivery = { pending: 1, sent: 120, failed: 3, retryable: 4 };
  const card = (props: Partial<Parameters<typeof DeliveryCard>[0]> = {}) => {
    const onRetry = vi.fn();
    render(<DeliveryCard delivery={delivery} targetType="mock_erp" retrying={false} onRetry={onRetry} {...props} />);
    return onRetry;
  };

  it("shows the four counts", () => {
    card();
    const counts = Object.fromEntries(
      screen.getAllByRole("term").map((term) => [term.textContent, term.nextElementSibling?.textContent]),
    );
    expect(counts).toEqual({ Sent: "120", Failed: "3", Pending: "1", "Can be resent": "4" });
  });

  it("names the target", () => {
    card();
    expect(screen.getByText(/Target: mock_erp/)).toBeInTheDocument();
  });

  it("says that resending is not limited to the selected time window", () => {
    card();
    expect(screen.getByText(/not only the ones in the selected window/)).toBeInTheDocument();
  });

  it("asks to resend when clicked", async () => {
    const onRetry = card();
    await userEvent.click(screen.getByRole("button", { name: "Resend failed deliveries" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("has nothing to resend: the button is off", () => {
    card({ delivery: { ...delivery, retryable: 0, failed: 0 } });
    expect(screen.getByRole("button", { name: "Resend failed deliveries" })).toBeDisabled();
  });

  it("locks the button and says so while resending", () => {
    card({ retrying: true });
    expect(screen.getByRole("button", { name: "Resending…" })).toBeDisabled();
  });

  it("says so when no target is configured, and offers nothing to resend", () => {
    card({ targetType: null });
    expect(screen.getByText(/No delivery target is configured/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("Sent")).not.toBeInTheDocument();
  });

  it("shows the counts without naming a target while the config is not known yet", () => {
    card({ targetType: undefined });
    expect(screen.queryByText(/Target:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend failed deliveries" })).toBeEnabled();
  });

  it("is a labelled region", () => {
    card();
    expect(screen.getByRole("region", { name: "Deliveries to the target system" })).toBeInTheDocument();
  });
});
