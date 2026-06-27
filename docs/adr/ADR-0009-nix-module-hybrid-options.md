# ADR-0009: CoachIQ Nix module hybrid options

## Status

**Accepted**, 2026-06-27. Supersedes the exhaustive hand-maintained Nix option mirror.

## Context

CoachIQ previously shipped its Nix packaging as a large flake plus a NixOS
module that mirrored the Pydantic `Settings` schema in `backend/core/config.py`
as hundreds of typed Nix options. That was a second configuration schema, kept
by hand in a different language.

The drift cost is real. HOF-018 found a production secret validation bug rooted
in config-layer mismatch, and HOF-020 review found many Nix-generated
`COACHIQ_*` keys that no longer matched the current Pydantic settings tree.
CoachIQ also has one known NixOS consumer owned by the maintainer, so the
benefit of a large self-documenting option surface is small compared with the
maintenance cost.

Sibling fleet services use a smaller module shape: a few first-class options,
one freeform settings passthrough, and `environmentFile` for secrets. CoachIQ's
configuration surface is larger than those services, so a pure freeform module
would lose useful structure for the load-bearing knobs.

## Decision

Use a hybrid NixOS module in the fleet layout:

- Keep `flake.nix` thin, with package definitions in `nix/package.nix` and the
  NixOS module in `nix/module.nix`.
- Expose the module as `nixosModules.default` under the NixOS namespace
  `services.coachiq`.
- Keep only load-bearing, interdependent, or easy-to-mistype settings as
  first-class Nix options: `enable`, `package`, `host`, `port`, `dataDir`,
  `environmentFile`, `openFirewall`, `logLevel`, and
  `tlsTerminationIsExternal`.
- Pass every other non-secret setting through `settings = attrsOf (oneOf [ str
  int bool ])`, using current `COACHIQ_*` environment variable names from the
  Pydantic `Settings` schema.
- Put secrets in `environmentFile` only. Do not put secret values in Nix options
  or the Nix store. The backend still supports direct env vars and `_FILE`
  readers, but the Nix module exposes one first-class secret interface.
- Track the consumer channel, `nixos-25.11`, instead of `nixpkgs-unstable`.

Freeform encoding rule: scalar booleans and integers may use native Nix values;
floats must be quoted strings; list and dictionary settings should be JSON
strings unless the specific Pydantic field parser is known to accept another
format such as comma-separated values.

## Consequences

### Becomes easier

- Adding or renaming backend settings no longer requires duplicating the schema
  in Nix.
- The Nix module stays small enough to review and test.
- Secrets stay out of the world-readable Nix store.

### Becomes harder

- Most settings lose Nix eval-time type checking and discoverability. Pydantic
  validation becomes the source of truth for the long tail.
- Operators must know the current `COACHIQ_*` env-var names and encoding rules
  for freeform settings.

### Cannot do anymore

- Do not rely on a parallel exhaustive Nix option mirror for application config.
- Do not place secret values in Nix module options.

## Alternatives considered

- **Keep the exhaustive typed mirror**: Provides more `nixos-option`
  discoverability, but it demonstrably drifts from the backend and is expensive
  to maintain for a single known consumer.
- **Pure freeform module**: Minimizes Nix code, but CoachIQ's larger config
  surface still benefits from first-class options for the few deployment knobs
  that are load-bearing or easy to mistype.

## Revisit conditions

- CoachIQ gains multiple independent out-of-tree NixOS consumers who need a
  richer typed option surface.
- A repeated class of production misconfiguration would clearly have been
  prevented by adding a specific first-class option.

## See also

- `nix/module.nix`
- `nix/package.nix`
- `backend/core/config.py`
- ADR-0008: RVC config facade naming
