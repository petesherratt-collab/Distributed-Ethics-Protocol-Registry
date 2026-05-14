# Distributed Ethics — Protocol Registry

Reference implementation for the blockchain governance framework described in:

> **Distributed Ethics: A Blockchain Governance Framework for AI Deployment**  
> Pete Sherratt, 2025  
> Zenodo Working Paper · Abstract ID https://doi.org/10.5281/zenodo.20179590

This repository contains two components:

- **`contracts/ProtocolRegistry.sol`** — a Solidity smart contract that issuing authorities (professional bodies, NGOs, regulators) use to publish the SHA-256 fingerprint of their ethics protocol documents to a public blockchain.
- **`cli/ethics_verify.py`** — a Python CLI that deploying organisations use to register protocol documents on-chain and verify that a local copy matches the immutable record.

Together they implement the core mechanism described in §2 of the paper: tamper-evident, publicly verifiable, cryptographic governance records for AI deployment ethics — requiring no central enforcement authority, no international treaty, and no modification to underlying AI architecture.

---

## How it works

An issuing authority produces an operational ethics protocol document (not a statement of values — a testable specification). They compute its SHA-256 hash and publish it to the registry contract. The hash is a 32-byte fingerprint: unique to the exact content of the document, irreversible, and unalterable after publication.

A deploying organisation loads the verified document into their AI system's reference context and instructs the system to treat it as constitutionally authoritative. At deployment — and at intervals specified by the protocol document itself — they run `verify` to confirm the loaded document still matches the on-chain record.

Any third party (auditor, regulator, parent, journalist) can independently run the same check. The verification result is a true/false operation that requires no trusted intermediary.

---

## Quick start

```bash
pip install -r cli/requirements.txt
cp .env.example .env
# fill in REGISTRY_RPC, REGISTRY_CONTRACT, REGISTRY_PRIVATE_KEY
```

**Deploy the contract** (once, by the issuing authority):

```bash
# Via Remix IDE: paste contracts/ProtocolRegistry.sol, compile 0.8.20, deploy to Sepolia
# Or with py-solc-x installed:
pip install py-solc-x
python cli/ethics_verify.py deploy
```

**Register a protocol document:**

```bash
python cli/ethics_verify.py register protocol.pdf \
    --name "Child AI Safeguarding Protocol v1 — SafeChild Coalition"
# → version 1 registered; tx hash printed
```

**Verify a local document against the chain:**

```bash
python cli/ethics_verify.py verify protocol.pdf \
    --authority 0xYOUR_AUTHORITY_ADDRESS
# → PASS or FAIL; exits 0/1 for use in deployment scripts and CI
```

**List all registered versions for an authority:**

```bash
python cli/ethics_verify.py list --authority 0xYOUR_AUTHORITY_ADDRESS
```

**Compute a document hash without touching the chain:**

```bash
python cli/ethics_verify.py hash protocol.pdf
```

---

## Contract

The `ProtocolRegistry` contract stores only:

- The SHA-256 hash of the protocol document (`bytes32`)
- The registering authority's Ethereum address
- A human-readable name
- The block timestamp of registration

No document content, no personal data, no author identity beyond the Ethereum address. The hash is a one-way function; the document cannot be reconstructed from it. Verification is a local true/false comparison — nothing is revealed to the chain.

Registered versions are immutable. They cannot be overwritten or deleted. The full version history is permanently and publicly readable.

---

## Environment variables

| Variable | Purpose |
|---|---|
| `REGISTRY_RPC` | JSON-RPC endpoint (default: `https://rpc.sepolia.org`) |
| `REGISTRY_CONTRACT` | Deployed contract address |
| `REGISTRY_PRIVATE_KEY` | Issuing-authority wallet key (register/deploy only) |

Copy `.env.example` to `.env`. Never commit `.env`.

---

## Relationship to the paper

The paper (SSRN [6719078](https://ssrn.com/abstract=6719078)) proposes this framework and argues the case for it. This repository is the reference implementation — the point at which the proposal becomes a specification with working code.

The paper also describes components not implemented here: the Merkle Tree batcher for agent-scale deployments (§4.4), the session summary hash chain for the AI Psychologist sentinel (Appendix B), and agent-native blockchain verification (§2.5). Those are the natural next extensions.

---

## License

MIT — see [LICENSE](LICENSE).
