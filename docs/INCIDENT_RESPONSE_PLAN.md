# Security Incident Response Plan

**Organization:** [Company name]
**Scope:** Amazon Information obtained through the Amazon Selling Partner API (SP-API) and the internal amazon-mcp tool
**Version:** 1.0
**Effective date:** 2026-09-27
**Next review:** 2027-03-27 (reviewed every 6 months)

## 1. Purpose

This plan defines how we detect, respond to, and report security incidents that affect Amazon Information or the credentials used to access it.

## 2. Roles and responsibilities

| Role | Person | Responsibilities |
|---|---|---|
| Incident Owner | [Name, e-mail, phone] | Detects and assesses incidents, contains them, notifies Amazon, documents the incident, and reviews this plan. |
| Backup contact | [Name, e-mail, phone, or "none"] | Takes over if the Incident Owner is unavailable. |

## 3. What counts as a security incident

- Loss or theft of a computer or device that stores SP-API credentials or Amazon Information.
- Malware, ransomware, or unauthorized remote access on such a device.
- SP-API credentials (LWA client secret, refresh token) exposed, e.g. committed to a code repository, sent by e-mail or chat, or shared with an unauthorized person.
- Unauthorized login to Seller Central or unexpected activity in the seller account or through the API.
- Any unauthorized access to, disclosure of, or modification of Amazon Information.

## 4. Response procedure

1. **Detect and record** – note the date and time of detection and what was observed.
2. **Contain (immediately)**
   - Rotate the LWA client secret in Seller Central (Develop Apps) and revoke the app authorization to invalidate the refresh token.
   - Change the Seller Central password and verify MFA settings.
   - Disconnect the affected device from the network and stop the amazon-mcp tool.
3. **Notify Amazon (within 24 hours of detection)** – e-mail **security@amazon.com** with: description of the incident, time of detection, affected data and credentials, containment actions taken, and contact details.
4. **Investigate and eradicate** – run a full antivirus scan, remove the cause (malware, leaked file, compromised account), and check API and account activity for misuse.
5. **Recover** – issue new credentials, update the local `.env` file, and resume operation only after the device is confirmed clean.
6. **Document and learn** – record the incident, actions, and timeline in the incident log below, and update this plan if needed.

## 5. Preventive controls

- SP-API credentials are stored only in a local `.env` file excluded from version control; they are never hard-coded, shared, or stored in public repositories.
- Only authorized personnel have access to the device and Seller Central account.
- Multi-factor authentication is enabled on Seller Central; passwords are at least 12 characters with special characters and are changed at least once a year.
- The operating system and antivirus are kept up to date.
- All communication with Amazon SP-API uses encrypted HTTPS (TLS).

## 6. Plan review

This plan is reviewed every 6 months and after every incident. Each review is recorded below.

| Date | Reviewed by | Changes |
|---|---|---|
| 2026-09-27 | [Name] | Initial version |

## 7. Incident log

| Date detected | Description | Actions taken | Amazon notified (date/time) |
|---|---|---|---|
| | | | |
