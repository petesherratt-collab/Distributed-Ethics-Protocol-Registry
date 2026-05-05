// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * ProtocolRegistry — Distributed Ethics Framework
 *
 * Issuing authorities (professional bodies, NGOs, regulators) publish the
 * SHA-256 hash of their ethics protocol document here. Any deploying
 * organisation or independent auditor can then verify that a local copy
 * of the document is the genuine, unmodified version that was registered.
 *
 * Nothing about the document itself is stored on-chain — only its 32-byte
 * fingerprint, the registering address, a human-readable name, and the
 * block timestamp. The hash is a one-way function; it cannot be used to
 * reconstruct the document.
 *
 * Deploy once to a public chain (Sepolia testnet or Ethereum mainnet).
 * The contract address becomes the public anchor for all verifications.
 */
contract ProtocolRegistry {

    struct ProtocolVersion {
        bytes32 docHash;      // SHA-256 of the off-chain protocol document
        uint256 registeredAt; // block.timestamp at registration
        string  name;         // human-readable name / short description
        bool    exists;
    }

    // authority address => version number => record
    mapping(address => mapping(uint256 => ProtocolVersion)) private _protocols;

    // authority address => highest version number registered (0 means none)
    mapping(address => uint256) public latestVersion;

    event ProtocolRegistered(
        address indexed authority,
        uint256 indexed version,
        bytes32         docHash,
        string          name,
        uint256         registeredAt
    );

    // -----------------------------------------------------------------------
    // Write
    // -----------------------------------------------------------------------

    /**
     * Register a new protocol version. The caller's address becomes the
     * immutable issuing authority for this record. Versions are assigned
     * sequentially starting at 1; they can never be overwritten or deleted.
     *
     * @param docHash  SHA-256 hash of the protocol document (bytes32)
     * @param name     Short human-readable description, e.g.
     *                 "Child AI Safeguarding Protocol v1 — SafeChild Coalition"
     * @return version The version number assigned to this registration
     */
    function register(bytes32 docHash, string calldata name)
        external
        returns (uint256 version)
    {
        require(docHash != bytes32(0), "ProtocolRegistry: hash required");
        require(bytes(name).length > 0,  "ProtocolRegistry: name required");
        require(bytes(name).length <= 256, "ProtocolRegistry: name too long");

        version = latestVersion[msg.sender] + 1;
        latestVersion[msg.sender] = version;

        _protocols[msg.sender][version] = ProtocolVersion({
            docHash:      docHash,
            registeredAt: block.timestamp,
            name:         name,
            exists:       true
        });

        emit ProtocolRegistered(msg.sender, version, docHash, name, block.timestamp);
    }

    // -----------------------------------------------------------------------
    // Read
    // -----------------------------------------------------------------------

    /**
     * Return a specific registered version.
     */
    function getVersion(address authority, uint256 version)
        external view
        returns (
            bytes32 docHash,
            uint256 registeredAt,
            string  memory name
        )
    {
        ProtocolVersion storage p = _protocols[authority][version];
        require(p.exists, "ProtocolRegistry: version not found");
        return (p.docHash, p.registeredAt, p.name);
    }

    /**
     * Return the most recently registered version for an authority.
     */
    function getLatest(address authority)
        external view
        returns (
            uint256 version,
            bytes32 docHash,
            uint256 registeredAt,
            string  memory name
        )
    {
        version = latestVersion[authority];
        require(version > 0, "ProtocolRegistry: no versions registered");
        ProtocolVersion storage p = _protocols[authority][version];
        return (version, p.docHash, p.registeredAt, p.name);
    }

    /**
     * Verify that a local document matches a registered record.
     *
     * Pass version = 0 to check against the latest registered version.
     * Returns true only if the version exists and the hashes match exactly.
     * Safe to call from off-chain tooling with eth_call — no gas cost.
     *
     * @param authority   Ethereum address of the issuing authority
     * @param version     Version number to check (0 = latest)
     * @param docHash     SHA-256 hash of the local document to verify
     */
    function verify(address authority, uint256 version, bytes32 docHash)
        external view
        returns (
            bool   matches,
            uint256 registeredAt,
            string  memory name
        )
    {
        uint256 v = version == 0 ? latestVersion[authority] : version;
        require(v > 0, "ProtocolRegistry: no versions registered");
        ProtocolVersion storage p = _protocols[authority][v];
        require(p.exists, "ProtocolRegistry: version not found");
        return (p.docHash == docHash, p.registeredAt, p.name);
    }
}
