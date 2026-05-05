#!/usr/bin/env python3
"""
Distributed Ethics — Protocol Registry CLI

Commands
--------
  hash      Compute the SHA-256 hash of a document (no blockchain needed)
  deploy    Compile and deploy the ProtocolRegistry contract
  register  Hash a document and publish it as a new protocol version on-chain
  verify    Verify a local document against an on-chain record (exits 0/1)
  list      List all registered versions for an issuing authority

Environment variables (or .env file)
-------------------------------------
  REGISTRY_RPC          Ethereum JSON-RPC endpoint  (default: Sepolia public)
  REGISTRY_CONTRACT     Deployed contract address
  REGISTRY_PRIVATE_KEY  Issuing-authority private key  (register/deploy only)
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

load_dotenv()

# ---------------------------------------------------------------------------
# Contract ABI
# ---------------------------------------------------------------------------

REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "docHash", "type": "bytes32"},
            {"internalType": "string",  "name": "name",    "type": "string"},
        ],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "version", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "authority", "type": "address"},
            {"internalType": "uint256", "name": "version",   "type": "uint256"},
        ],
        "name": "getVersion",
        "outputs": [
            {"internalType": "bytes32", "name": "docHash",      "type": "bytes32"},
            {"internalType": "uint256", "name": "registeredAt", "type": "uint256"},
            {"internalType": "string",  "name": "name",         "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "authority", "type": "address"},
        ],
        "name": "getLatest",
        "outputs": [
            {"internalType": "uint256", "name": "version",      "type": "uint256"},
            {"internalType": "bytes32", "name": "docHash",      "type": "bytes32"},
            {"internalType": "uint256", "name": "registeredAt", "type": "uint256"},
            {"internalType": "string",  "name": "name",         "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "authority", "type": "address"},
            {"internalType": "uint256", "name": "version",   "type": "uint256"},
            {"internalType": "bytes32", "name": "docHash",   "type": "bytes32"},
        ],
        "name": "verify",
        "outputs": [
            {"internalType": "bool",    "name": "matches",     "type": "bool"},
            {"internalType": "uint256", "name": "registeredAt","type": "uint256"},
            {"internalType": "string",  "name": "name",        "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "latestVersion",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "address", "name": "authority",    "type": "address"},
            {"indexed": True,  "internalType": "uint256", "name": "version",      "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "docHash",      "type": "bytes32"},
            {"indexed": False, "internalType": "string",  "name": "name",         "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "registeredAt", "type": "uint256"},
        ],
        "name": "ProtocolRegistered",
        "type": "event",
    },
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

DEFAULT_RPC = "https://rpc.sepolia.org"


def _sha256(path: Path) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()


def _connect(rpc: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc))
    # POA middleware keeps Sepolia / Polygon / BSC from choking on extra fields
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        raise click.ClickException(f"Cannot connect to RPC endpoint: {rpc}")
    return w3


def _contract(w3: Web3, address: str):
    return w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=REGISTRY_ABI,
    )


def _fmt_ts(unix: int) -> str:
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _send(w3, account, fn):
    """Build, sign, and broadcast a transaction; wait for receipt."""
    nonce = w3.eth.get_transaction_count(account.address)
    tx = fn.build_transaction({"from": account.address, "nonce": nonce})
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("1.0.0")
def cli():
    """Distributed Ethics — Protocol Registry CLI.

    Publish and verify on-chain cryptographic records for AI ethics protocols.
    """


# ---------------------------------------------------------------------------
# hash
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def hash(file):
    """Compute the SHA-256 hash of FILE.

    No network connection required. Use this to check what hash will be
    registered before committing a transaction.
    """
    digest = _sha256(Path(file))
    click.echo("0x" + digest.hex())


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--rpc",      envvar="REGISTRY_RPC",         default=DEFAULT_RPC, show_default=True)
@click.option("--key",      envvar="REGISTRY_PRIVATE_KEY", required=True,
              help="Private key of the deploying wallet")
@click.option("--sol", "sol_path",
              default=str(Path(__file__).parent.parent / "contracts" / "ProtocolRegistry.sol"),
              show_default=True,
              help="Path to ProtocolRegistry.sol")
def deploy(rpc, key, sol_path):
    """Compile ProtocolRegistry.sol and deploy it to the network.

    Requires py-solc-x:  pip install py-solc-x

    After deployment, set REGISTRY_CONTRACT=<address> in your .env file.
    """
    try:
        from solcx import compile_files, install_solc, get_installed_solc_versions
    except ImportError:
        raise click.ClickException(
            "py-solc-x is required for deployment.\n"
            "Install it with:  pip install py-solc-x\n"
            "Or deploy via Remix IDE (https://remix.ethereum.org) and paste the "
            "contract address into REGISTRY_CONTRACT in your .env file."
        )

    solc_version = "0.8.20"
    if solc_version not in [str(v) for v in get_installed_solc_versions()]:
        click.echo(f"Downloading solc {solc_version}...")
        install_solc(solc_version)

    click.echo(f"Compiling {sol_path}...")
    compiled = compile_files(
        [sol_path],
        output_values=["abi", "bin"],
        solc_version=solc_version,
    )
    contract_id = f"{sol_path}:ProtocolRegistry"
    bytecode = compiled[contract_id]["bin"]

    w3 = _connect(rpc)
    account = w3.eth.account.from_key(key)
    click.echo(f"Deployer : {account.address}")
    click.echo(f"Network  : chain {w3.eth.chain_id}")

    factory = w3.eth.contract(abi=REGISTRY_ABI, bytecode=bytecode)
    receipt = _send(w3, account, factory.constructor())

    if receipt.status != 1:
        raise click.ClickException("Deployment transaction failed.")

    addr = receipt.contractAddress
    click.secho(f"\nDeployed at: {addr}", fg="green", bold=True)
    click.echo(f"Block      : {receipt.blockNumber}")
    click.echo(f"Tx         : {receipt.transactionHash.hex()}")
    click.echo(f"\nAdd to .env:  REGISTRY_CONTRACT={addr}")


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--name", required=True,
              help="Protocol name, e.g. 'Child AI Safeguarding Protocol v1'")
@click.option("--rpc",      envvar="REGISTRY_RPC",         default=DEFAULT_RPC, show_default=True)
@click.option("--contract", envvar="REGISTRY_CONTRACT",    required=True,
              help="Deployed ProtocolRegistry contract address")
@click.option("--key",      envvar="REGISTRY_PRIVATE_KEY", required=True,
              help="Private key of the issuing-authority wallet")
def register(file, name, rpc, contract, key):
    """Hash FILE and publish it as a new protocol version on-chain.

    The wallet identified by --key becomes the immutable issuing authority
    for this record. Version numbers are assigned sequentially from 1.
    """
    path = Path(file)
    digest = _sha256(path)

    click.echo(f"Document : {path.name}")
    click.echo(f"SHA-256  : 0x{digest.hex()}")

    w3 = _connect(rpc)
    account = w3.eth.account.from_key(key)
    reg = _contract(w3, contract)

    click.echo(f"Authority: {account.address}")
    click.echo(f"Network  : chain {w3.eth.chain_id}")
    click.echo("Sending transaction...", nl=False)

    receipt = _send(w3, account, reg.functions.register(digest, name))
    click.echo(" confirmed.")

    if receipt.status != 1:
        raise click.ClickException("Transaction reverted.")

    logs = reg.events.ProtocolRegistered().process_receipt(receipt)
    version = logs[0]["args"]["version"] if logs else "?"

    click.secho(f"\nRegistered as version {version}.", fg="green", bold=True)
    click.echo(f"Block    : {receipt.blockNumber}")
    click.echo(f"Tx       : {receipt.transactionHash.hex()}")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--authority", required=True,
              help="Ethereum address of the issuing authority")
@click.option("--version", "ver", default=0, show_default=True,
              help="Version number to check (0 = latest)")
@click.option("--rpc",      envvar="REGISTRY_RPC",      default=DEFAULT_RPC, show_default=True)
@click.option("--contract", envvar="REGISTRY_CONTRACT", required=True,
              help="Deployed ProtocolRegistry contract address")
def verify(file, authority, ver, rpc, contract):
    """Verify that FILE matches the on-chain record for AUTHORITY.

    Exits 0 on match, 1 on mismatch or error. Safe to use in deployment
    scripts, CI pipelines, and scheduled verification jobs.

    Example — check latest version:

    \b
        python ethics_verify.py verify protocol.pdf \\
            --authority 0xABC... \\
            --contract  0xDEF...

    Example — check a specific version:

    \b
        python ethics_verify.py verify protocol.pdf \\
            --authority 0xABC... \\
            --version   2 \\
            --contract  0xDEF...
    """
    path = Path(file)
    digest = _sha256(path)

    click.echo(f"Document  : {path.name}")
    click.echo(f"SHA-256   : 0x{digest.hex()}")

    w3 = _connect(rpc)
    reg = _contract(w3, contract)
    auth = Web3.to_checksum_address(authority)

    # The contract handles version=0 → latest internally, but we echo which
    # version was resolved so the output is unambiguous.
    resolved_ver = ver
    if ver == 0:
        resolved_ver = reg.functions.latestVersion(auth).call()
        if resolved_ver == 0:
            raise click.ClickException(f"No versions registered for {authority}")
        click.echo(f"Version   : {resolved_ver} (latest)")
    else:
        click.echo(f"Version   : {ver}")

    matches, registered_at, name = reg.functions.verify(auth, resolved_ver, digest).call()

    click.echo(f"Authority : {auth}")
    click.echo(f"Name      : {name}")
    click.echo(f"Registered: {_fmt_ts(registered_at)}")
    click.echo()

    if matches:
        click.secho("PASS — document matches the on-chain record.", fg="green", bold=True)
        sys.exit(0)
    else:
        click.secho("FAIL — document does NOT match the on-chain record.", fg="red", bold=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.option("--authority", required=True,
              help="Ethereum address of the issuing authority")
@click.option("--rpc",      envvar="REGISTRY_RPC",      default=DEFAULT_RPC, show_default=True)
@click.option("--contract", envvar="REGISTRY_CONTRACT", required=True,
              help="Deployed ProtocolRegistry contract address")
def list_versions(authority, rpc, contract):
    """List all registered protocol versions for an issuing authority."""
    w3 = _connect(rpc)
    reg = _contract(w3, contract)
    auth = Web3.to_checksum_address(authority)

    latest = reg.functions.latestVersion(auth).call()
    if latest == 0:
        click.echo(f"No versions registered for {authority}")
        return

    click.echo(f"Authority: {auth}")
    click.echo()
    click.echo(f"{'Ver':>4}  {'Registered (UTC)':>22}  {'SHA-256':64}  Name")
    click.echo("-" * 130)

    for v in range(1, latest + 1):
        doc_hash, registered_at, name = reg.functions.getVersion(auth, v).call()
        click.echo(
            f"{v:>4}  {_fmt_ts(registered_at):>22}  "
            f"0x{doc_hash.hex()}  {name}"
        )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
