import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmingIconButton } from "../location";

describe("ConfirmingIconButton", () => {
  it("shows the armed action before the second tap confirms", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmingIconButton
        icon={<span aria-hidden>!</span>}
        label="Delete trip"
        confirmLabel="Tap again to delete trip"
        onConfirm={onConfirm}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete trip" }));

    expect(screen.getByText("Tap again to delete trip")).toBeVisible();
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Tap again to delete trip" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
