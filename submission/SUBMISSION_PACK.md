# ClearTrace — Submission Pack

**Status:** Submission draft. Team name, problem statement, repository, and PDF link are filled in; the LinkedIn video still needs to be recorded and posted by the team.

| Submission field | Ready value | Status |
| --- | --- | --- |
| Team name | **ClearTrace** | Confirmed by the team |
| Selected problem statement | **Problem 01 — DataFix: Autonomous Data Quality and Repair Engine** | Confirmed in project notes |
| LinkedIn video link (maximum 3 minutes) | **[ADD LINK AFTER RECORDING AND POSTING]** | Recording/posting requires the team member |
| Public GitHub repository | https://github.com/Rohibuilds/cleartrace-data-quality | Public source repository |
| PDF Google Drive link | https://drive.google.com/file/d/1FgS0zYRWO__PD7LR_bAVrrM9dbwM0PTe/view?usp=sharing | Anyone with the link can view |
| Deployed app | https://cleartrace-web-production.up.railway.app/ | Judge sample path requires no sign-in; personal work uses email OTP |

## Accurate product description

ClearTrace is a review-first data quality workspace. It inspects data, explains detected issues, offers suggested repairs for human review, records approved changes, revalidates the dataset, and exports cleaned data and audit information. It supports CSV and spreadsheet workflows, deterministic issue checks, mathematical validation, revision history, comparison, and a mobile PWA shell.

The public judge preview uses synthetic sample data in a temporary workspace. Judges can inspect and apply repairs; uploads are blocked. Personal workspaces use email one-time codes; Gmail delivery must be configured in Railway before that sign-in path can be used. Login activity alert emails are not part of this OTP flow. Do not describe other email/SMS alerts as operational unless separately configured and verified. Do not use this demo for confidential customer data.

## Three-minute video outline

Use [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Keep the final recording under 3:00; target 2:30–2:45 to allow for LinkedIn processing and a small timing buffer. Show the running app on a phone-sized viewport or phone, and avoid exposing one-time codes, private inboxes, or personal data.

## Judge access

Judges can choose the no-sign-in sample workspace. Email OTP remains available for personal workspaces after Gmail SMTP is configured in Railway. The judge workspace expires automatically and does not accept file uploads.

## Before submitting

- Record and post the demo video, verify its visibility, and add the LinkedIn URL.
- Configure Gmail SMTP in Railway if personal email OTP sign-in should be demonstrated.
- Check the deployed app from a second browser/device and confirm the public sample judge workspace opens.
- Read current event rules, especially team naming, AI/tool disclosure, code reuse, build-window, and public-access requirements.
