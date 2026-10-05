import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LABELS } from "../test/reviewServer";
import { LabelPicker } from "./LabelPicker";
import { Notice } from "./Notice";
import { Pager } from "./Pager";

describe("LabelPicker", () => {
  const picker = (props: Partial<Parameters<typeof LabelPicker>[0]> = {}) =>
    render(<LabelPicker requestId={7} labels={LABELS} suggested={null} onChoose={() => {}} {...props} />);

  it("has one button per label", () => {
    picker();
    expect(screen.getAllByRole("button")).toHaveLength(LABELS.length);
  });

  it("reports the label that was clicked", async () => {
    const onChoose = vi.fn();
    picker({ onChoose });
    await userEvent.click(screen.getByRole("button", { name: "damaged_card" }));
    expect(onChoose).toHaveBeenCalledExactlyOnceWith("damaged_card");
  });

  it("does not choose anything by itself, even with a suggestion", () => {
    const onChoose = vi.fn();
    picker({ suggested: "report_fraud", onChoose });
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("marks a suggestion that is not among the labels as nothing at all", () => {
    picker({ suggested: "not_a_label" });
    expect(screen.queryByText("suggested")).not.toBeInTheDocument();
  });

  it("disables every button when disabled", async () => {
    const onChoose = vi.fn();
    picker({ disabled: true, onChoose });
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
    await userEvent.click(screen.getAllByRole("button")[0] as HTMLElement);
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("has no title for a label without a description", () => {
    picker();
    expect(screen.getByRole("button", { name: "card_declined" })).not.toHaveAttribute("title");
  });

  it("can be used with the keyboard", async () => {
    const onChoose = vi.fn();
    picker({ onChoose });
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    expect(onChoose).toHaveBeenCalledWith(LABELS[0]?.name);
  });

  it("copes with no labels", () => {
    picker({ labels: [] });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByRole("group")).toBeInTheDocument();
  });
});

describe("Pager", () => {
  const pager = (props: Partial<Parameters<typeof Pager>[0]> = {}) => {
    const onPageChange = vi.fn();
    render(<Pager page={1} pageSize={20} shown={20} total={87} onPageChange={onPageChange} {...props} />);
    return onPageChange;
  };

  it("describes the range", () => {
    pager();
    expect(screen.getByText("21-40 of 87")).toBeInTheDocument();
  });

  it("goes to the previous and the next page", async () => {
    const onPageChange = pager();
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange.mock.calls).toEqual([[0], [2]]);
  });

  it("cannot go before the first page", () => {
    pager({ page: 0 });
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("cannot go past the last page", () => {
    pager({ page: 4, shown: 7 });
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
  });

  it("has one page when everything fits", () => {
    pager({ page: 0, shown: 5, total: 5 });
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("disables both buttons while a page loads", () => {
    pager({ disabled: true });
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("is a labelled navigation landmark", () => {
    pager();
    expect(screen.getByRole("navigation", { name: "Pages of the review queue" })).toBeInTheDocument();
  });
});

describe("Notice", () => {
  it("shows its message and kind", () => {
    const { container } = render(<Notice kind="success" message="Saved." />);
    expect(screen.getByText("Saved.")).toBeInTheDocument();
    expect(container.querySelector("[data-kind]")).toHaveAttribute("data-kind", "success");
  });

  it("has no dismiss button unless it can be dismissed", () => {
    render(<Notice kind="info" message="FYI" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("can be dismissed", async () => {
    const onDismiss = vi.fn();
    render(<Notice kind="error" message="Oops" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
