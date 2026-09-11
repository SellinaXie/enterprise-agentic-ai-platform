# Security Policy

## Project status

This repository is a production-minded portfolio and reference implementation. It is not a
certified production service and does not replace an organization's security, privacy, risk, or
compliance controls.

V8A provides container, configuration, logging, error-handling, and database-integration
foundations. Authentication, authorization, tenant isolation, authenticated reviewer identity,
managed-secret integration, deployment hardening, and continuous production monitoring are not
implemented.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's private vulnerability
reporting feature when it is enabled for this repository. Otherwise, contact the repository owner
through the contact method on their GitHub profile and ask for a private reporting channel before
sharing technical details.

Do not include real credentials, API keys, client data, proprietary documents, regulated data, or
working exploit payloads in a public issue. There is no claim of a staffed enterprise incident
response team or guaranteed response time.

## Secrets and data

Use environment variables or a deployment platform's secret injection. Never commit `.env`, real
database passwords, provider keys, production documents, or customer assessment data. Rotate any
credential immediately if it is accidentally disclosed.
