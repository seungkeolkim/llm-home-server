"""공식 APK의 v2 서명과 APK 전체 content digest를 기존 Git OpenSSL로 검증합니다."""

import hashlib
import json
from pathlib import Path
import struct
import subprocess

from service_runtime import WORKSPACE_DIRECTORY, RUNTIME_DIRECTORY


def read_length_prefixed(content, offset=0):
    """APK v2의 uint32 길이 필드를 경계 검사와 함께 읽습니다."""
    if offset + 4 > len(content):
        raise ValueError("서명 구조의 길이 필드가 잘렸습니다.")
    content_length = struct.unpack_from("<I", content, offset)[0]
    content_end = offset + 4 + content_length
    if content_end > len(content):
        raise ValueError("서명 구조가 선언한 길이보다 짧습니다.")
    return content[offset + 4:content_end], content_end


def main():
    """APK content digest, RSA 서명과 signer certificate의 public key 일치를 확인합니다."""
    apk_path = WORKSPACE_DIRECTORY / "data/PiCodingAgent/downloads/pi-remote-0.7.7-android-arm64.apk"
    content = apk_path.read_bytes()
    end_record_offset = content.rfind(b"PK\x05\x06", max(0, len(content) - 65557))
    if end_record_offset < 0:
        raise ValueError("ZIP End Record가 없습니다.")
    central_directory_offset = struct.unpack_from("<I", content, end_record_offset + 16)[0]
    if content[central_directory_offset - 16:central_directory_offset] != b"APK Sig Block 42":
        raise ValueError("APK Signing Block이 없습니다.")
    signing_block_size = struct.unpack_from("<Q", content, central_directory_offset - 24)[0]
    signing_block_offset = central_directory_offset - signing_block_size - 8
    if struct.unpack_from("<Q", content, signing_block_offset)[0] != signing_block_size:
        raise ValueError("APK Signing Block 크기가 일치하지 않습니다.")
    pair_offset = signing_block_offset + 8
    signer_block = None
    while pair_offset < central_directory_offset - 24:
        pair_length = struct.unpack_from("<Q", content, pair_offset)[0]
        block_identifier = struct.unpack_from("<I", content, pair_offset + 8)[0]
        if block_identifier == 0x7109871A:
            signer_block = content[pair_offset + 12:pair_offset + 8 + pair_length]
        pair_offset += 8 + pair_length
    if signer_block is None:
        raise ValueError("지원하는 APK v2 서명이 없습니다.")
    signers, unused_offset = read_length_prefixed(signer_block)
    signer, unused_offset = read_length_prefixed(signers)
    signed_data, offset = read_length_prefixed(signer)
    signatures, offset = read_length_prefixed(signer, offset)
    public_key, offset = read_length_prefixed(signer, offset)
    signature_record, unused_offset = read_length_prefixed(signatures)
    algorithm_identifier = struct.unpack_from("<I", signature_record)[0]
    if algorithm_identifier != 0x0103:
        raise ValueError("이 검증기는 APK RSA PKCS1 SHA256 서명만 지원합니다.")
    signature, unused_offset = read_length_prefixed(signature_record, 4)
    digests, offset = read_length_prefixed(signed_data)
    certificates, offset = read_length_prefixed(signed_data, offset)
    certificate, unused_offset = read_length_prefixed(certificates)
    digest_record, unused_offset = read_length_prefixed(digests)
    if struct.unpack_from("<I", digest_record)[0] != algorithm_identifier:
        raise ValueError("APK digest와 signature algorithm이 다릅니다.")
    expected_digest, unused_offset = read_length_prefixed(digest_record, 4)
    patched_end_record = bytearray(content[end_record_offset:])
    struct.pack_into("<I", patched_end_record, 16, signing_block_offset)
    content_sections = [content[:signing_block_offset], content[central_directory_offset:end_record_offset], bytes(patched_end_record)]
    chunk_digests = []
    for section in content_sections:
        for chunk_offset in range(0, len(section), 1024 * 1024):
            chunk = section[chunk_offset:chunk_offset + 1024 * 1024]
            chunk_digests.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(chunk)) + chunk).digest())
    actual_digest = hashlib.sha256(b"\x5a" + struct.pack("<I", len(chunk_digests)) + b"".join(chunk_digests)).digest()
    if actual_digest != expected_digest:
        raise ValueError("APK의 전체 content digest가 일치하지 않습니다.")
    verification_directory = RUNTIME_DIRECTORY / "verification/apk"
    verification_directory.mkdir(parents=True, exist_ok=True)
    for file_name, file_content in {"certificate.der": certificate, "public-key.der": public_key,
                                    "signature.bin": signature, "signed-data.bin": signed_data}.items():
        (verification_directory / file_name).write_bytes(file_content)
    openssl_path = Path("C:/Program Files/Git/usr/bin/openssl.exe")
    certificate_public_key = subprocess.check_output([str(openssl_path), "x509", "-inform", "DER", "-in",
                                                      str(verification_directory / "certificate.der"), "-pubkey", "-noout"])
    (verification_directory / "public-key.pem").write_bytes(certificate_public_key)
    extracted_public_key = subprocess.check_output([str(openssl_path), "pkey", "-pubin", "-outform", "DER"], input=certificate_public_key)
    if extracted_public_key != public_key:
        raise ValueError("APK public key와 signer certificate가 일치하지 않습니다.")
    verified_signature = subprocess.check_output([str(openssl_path), "dgst", "-sha256", "-verify",
                                                  str(verification_directory / "public-key.pem"), "-signature",
                                                  str(verification_directory / "signature.bin"),
                                                  str(verification_directory / "signed-data.bin")], text=True).strip()
    certificate_details = subprocess.check_output([str(openssl_path), "x509", "-inform", "DER", "-in",
                                                   str(verification_directory / "certificate.der"), "-subject", "-dates", "-noout"], text=True)
    summary = {"file_sha256": hashlib.sha256(content).hexdigest(), "apk_v2_content_digest": "verified",
               "rsa_sha256_signature": verified_signature,
               "signer_certificate_sha256": hashlib.sha256(certificate).hexdigest(),
               "certificate": certificate_details.strip()}
    (verification_directory / "signature-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
