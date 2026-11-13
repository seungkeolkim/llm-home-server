import { randomUUID } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const runtimeRequire = createRequire(path.join(workspaceDirectory, "data/RemotePi/npm/package.json"));
const qrCodeRenderer = runtimeRequire("qrcode");
const artifactFileNames = ["pairing-qr-code.png", "pairing-code.txt", "pairing-status.json"];

/** 자신이 생성한 QR 파일만 제거하여 새 pairing code를 지우지 않습니다. */
function removeExpiredPairingArtifacts(artifactDirectory, publicationIdentifier) {
    try {
        const status = JSON.parse(fs.readFileSync(path.join(artifactDirectory, "pairing-status.json"), "utf8"));
        if (status.publicationIdentifier !== publicationIdentifier) return;
        for (const artifactFileName of artifactFileNames) {
            fs.rmSync(path.join(artifactDirectory, artifactFileName), { force: true });
        }
    }
    catch {
        return;
    }
}

/** 공식 Extension의 같은 URI를 Desktop에서 확인 가능한 로컬 PNG로 표시합니다. */
export async function publishPairingArtifacts(pairingDetails, artifactDirectory = path.join(workspaceDirectory, "runtime/RemotePi/pairing")) {
    const pairingUri = new URL(pairingDetails.uri);
    if (pairingUri.protocol !== "remotepi:" || pairingUri.hostname !== "pair" ||
        !pairingUri.searchParams.has("t") || !pairingUri.searchParams.has("epk")) {
        throw new Error("유효한 Remote Pi pairing URI가 필요합니다.");
    }
    const expiresAt = Number(pairingDetails.expiresAt);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        throw new Error("Pairing code의 유효기간이 만료됐습니다.");
    }
    fs.mkdirSync(artifactDirectory, { recursive: true });
    const publicationIdentifier = randomUUID();
    await qrCodeRenderer.toFile(path.join(artifactDirectory, "pairing-qr-code.png"), pairingDetails.uri, {
        errorCorrectionLevel: "M",
        margin: 4,
        scale: 8,
    });
    fs.writeFileSync(path.join(artifactDirectory, "pairing-code.txt"), pairingDetails.uri, { mode: 0o600 });
    const publicationStatus = {
        publicationIdentifier,
        expiresAt,
        agentName: pairingDetails.name,
        createdAt: new Date().toISOString(),
    };
    fs.writeFileSync(path.join(artifactDirectory, "pairing-status.json"), JSON.stringify(publicationStatus, null, 2));
    const expirationTimer = setTimeout(() => {
        removeExpiredPairingArtifacts(artifactDirectory, publicationIdentifier);
    }, Math.max(1, expiresAt - Date.now() + 100));
    expirationTimer.unref();
    return publicationStatus;
}
