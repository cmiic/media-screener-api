# Security Policy

## Reporting a vulnerability

Please report security issues **privately** using GitHub's [private vulnerability reporting](https://github.com/cmiic/media-screener-api/security/advisories/new). Do not open a public issue, pull request, or discussion for a suspected vulnerability.

If you cannot use GitHub advisories, email <c@miic.at>.

Please include the affected version or image digest, a description of the impact, and the smallest reproduction you can manage. You will get an acknowledgement, and a fix or an explanation of why the behaviour is intended. This is a small project maintained by one person, so please allow reasonable time before disclosing publicly.

## Supported versions

Only the most recent release receives security fixes. Released images are immutable and identified by digest; upgrade rather than expecting a patched rebuild of an old tag.

## Deployment assumptions

**This service has no authentication, by design.** It is a private internal service intended to be reached over a container network or loopback by a trusted caller. The standalone scripts bind the published port to `127.0.0.1` for that reason.

Before any cross-host deployment, terminate TLS and enforce service authentication and rate limits at a reverse proxy or gateway — mutually authenticated TLS is preferred. Publicly exposing an inference endpoint also invites abuse as free compute, which is unsupported.

The NudeNet model is not shipped in the image. It is provisioned by the operator and verified against a pinned SHA-256 at provisioning time and again at container start.

## What this service is not

Classification is **probabilistic and best-effort**. It is a screening aid for adult or explicit imagery. It is not a compliance control, not a content-moderation guarantee, and explicitly **not** illegal-imagery hash matching. Do not rely on it as a legal safeguard.

## In scope

- Remote code execution, container escape, or arbitrary file access through the classification endpoints — including via crafted PDF, video, DOCX, or PPTX input
- Bypass of the page, pixel, duration, frame, document-image, size, concurrency, or timeout limits leading to unbounded resource use
- Loading a model that fails checksum verification, or bypassing that verification
- Leaking submitted media, file contents, or exception detail to a caller

## Not a vulnerability

- **The absence of authentication.** It is intentional and documented above; exposing the service directly is a deployment error.
- **A misclassification.** False negatives and false positives are inherent to the model and are not security issues. See the model provenance section of the [README](README.md).
- Denial of service against a deployment that has been published to an untrusted network.
- Findings that require an already-compromised host or container runtime.
