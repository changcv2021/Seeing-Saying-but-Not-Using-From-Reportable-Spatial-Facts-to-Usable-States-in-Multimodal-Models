#!/usr/bin/env python3
"""CPU-only scientific-contract helpers; not a visual gold generator or model runner."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


def count(value: Any, name: str = "count") -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, not {value!r}")
    return value


@dataclass(frozen=True)
class Action:
    kind: str
    amount: int

    def __post_init__(self) -> None:
        if self.kind not in {"ADD", "REMOVE", "SET", "NOOP"}:
            raise ValueError(f"Unsupported action: {self.kind}")
        count(self.amount, "amount")
        if self.kind == "NOOP" and self.amount != 0:
            raise ValueError("NOOP requires amount=0")

    def apply(self, state: int) -> int:
        state = count(state, "state")
        if self.kind == "ADD":
            return state + self.amount
        if self.kind == "REMOVE":
            return count(state - self.amount, "result after REMOVE")
        if self.kind == "SET":
            return self.amount
        return state


@dataclass(frozen=True)
class Program:
    s0: int
    a1: Action
    a2: Action
    source_type: str = "SYMBOLIC_CONTROL"

    def __post_init__(self) -> None:
        count(self.s0, "s0")
        if self.source_type not in {"SYMBOLIC_CONTROL", "SOURCE_SUPPORTED_COUNT"}:
            raise ValueError("Use a declared source_type")
        if self.source_type == "SOURCE_SUPPORTED_COUNT" and (
            self.a1.kind == "SET" or self.a2.kind == "SET"
        ):
            raise ValueError("SET is a symbolic control here, not an inferred native action")
        _ = self.s2  # Validate every intermediate transition.

    @property
    def s1(self) -> int:
        return self.a1.apply(self.s0)

    @property
    def s2(self) -> int:
        return self.a2.apply(self.s1)

    def signatures(self, observed: Any) -> list[str]:
        # No forced mechanistic assignment when values coincide.
        if observed is None:
            return ["NULL"]
        if type(observed) is not int:
            return ["NON_INTEGER"]
        values = {"S0": self.s0, "S1": self.s1, "S2": self.s2,
                  "A1_AMOUNT": self.a1.amount, "A2_AMOUNT": self.a2.amount}
        hits = [name for name, val in values.items() if observed == val]
        return hits or ["OTHER_INTEGER"]

    def commutes_on_this_state(self) -> bool | None:
        try:
            reversed_result = self.a1.apply(self.a2.apply(self.s0))
        except ValueError:
            return None  # Reverse program inadmissible; not a negative example.
        return reversed_result == self.s2


def interchange(recipient: Program, donor: Program,
                recipient_prediction: Any = None) -> dict[str, Any]:
    """Keep recipient A2, substitute donor S1. Does not edit either program."""
    expected = recipient.a2.apply(donor.s1)
    collisions = []
    if donor.s1 == recipient.s1:
        collisions.append("S1_UNCHANGED")
    alternatives = {
        "RECIPIENT_FINAL": recipient.s2,
        "DONOR_FINAL": donor.s2,
        "DONOR_S1_COPY": donor.s1,
        "RECIPIENT_S0_COPY": recipient.s0,
    }
    for label, value in alternatives.items():
        if expected == value:
            collisions.append(label)
    if type(recipient_prediction) is int and expected == recipient_prediction:
        collisions.append("UNPATCHED_PREDICTION")
    return {
        "recipient_s1": recipient.s1,
        "donor_s1": donor.s1,
        "recipient_final_gold": recipient.s2,
        "donor_final_gold": donor.s2,
        "expected_counterfactual": expected,
        "collisions": collisions,
        "discriminative": not collisions,
    }


def paired_change(before_correct: bool, after_correct: bool) -> str:
    if type(before_correct) is not bool or type(after_correct) is not bool:
        raise ValueError("paired_change requires scored booleans, never unrun/null flags")
    if not before_correct and after_correct:
        return "RESCUE"
    if before_correct and not after_correct:
        return "HARM"
    return "STABLE_CORRECT" if before_correct else "STABLE_WRONG"


def anchor_can_see(anchor_end_exclusive: int, information_end_exclusive: int) -> bool:
    # A prefix anchor must follow the entire information span. Token offsets
    # must first be validated against the actual processor-expanded sequence.
    for name, val in [("anchor_end", anchor_end_exclusive),
                      ("information_end", information_end_exclusive)]:
        count(val, name)
    return anchor_end_exclusive >= information_end_exclusive


def check_partition(pair: Mapping[str, str]) -> None:
    allowed = {"LOCALIZE", "SELECT", "LOCKED_EVAL"}
    if pair.get("recipient_split") not in allowed or pair.get("donor_split") not in allowed:
        raise ValueError("Missing or unknown split")
    if pair["recipient_split"] != pair["donor_split"]:
        raise ValueError("Donor and recipient cross a locked partition")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Print a synthetic example only")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return
    r = Program(2, Action("ADD", 2), Action("REMOVE", 1))
    d = Program(2, Action("ADD", 3), Action("ADD", 2))
    print(json.dumps({"scope": "SYNTHETIC_DEMONSTRATION_NOT_MODEL_RESULT",
                      "recipient": asdict(r), "donor": asdict(d),
                      "interchange": interchange(r, d)}, indent=2))


if __name__ == "__main__":
    main()
