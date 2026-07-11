import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/login-form";

const { useAuthMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn()
}));

vi.mock("@/contexts", () => ({ useAuth: useAuthMock }));

function authContext(mode: "single" | "multi") {
  return {
    login: vi.fn(),
    sendMagicLink: vi.fn(),
    authStatus: {
      enabled: true,
      mode,
      jwt_available: true,
      magic_links_enabled: true,
      oidc_enabled: true
    },
    isLoading: false,
    statusError: null
  };
}

describe("LoginForm authentication methods", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows magic link and OIDC without an unusable password form in multi-user mode", () => {
    useAuthMock.mockReturnValue(authContext("multi"));

    render(<LoginForm />);

    expect(screen.getByRole("button", { name: "Sign in with PocketID" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Email" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Username" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("shows username and password without the magic-link form in single-user mode", () => {
    useAuthMock.mockReturnValue(authContext("single"));

    render(<LoginForm />);

    expect(screen.getByRole("textbox", { name: "Username" })).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Email" })).not.toBeInTheDocument();
  });

  it("shows a branded connection state while authentication is loading", () => {
    useAuthMock.mockReturnValue({
      ...authContext("single"),
      authStatus: null,
      isLoading: true
    });

    render(<LoginForm />);

    expect(screen.getByText("Connecting to CoachIQ")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Connecting...");
  });
});
