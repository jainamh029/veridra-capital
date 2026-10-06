// Real synthetic notices pulled from synthetic_data/output/capital_calls.jsonl, used to give
// the Verification console something real to run without requiring the user to author a notice
// by hand. sender_domain is passed explicitly where the notice body's From: header differs from
// the mail envelope (see BUILD_LOG.md's fund_admin_email note) — exactly how the real pipeline
// is fed in tests/demo_batch.

export interface SampleNotice {
  key: string;
  label: string;
  kind: "clean" | "fraud";
  fraudType?: string;
  notice_text: string;
  sender_domain?: string;
  sender_email?: string;
}

export const SAMPLE_NOTICES: SampleNotice[] = [
  {
    key: "clean-fieldstone",
    label: "Clean — Fieldstone Equity Partners II",
    kind: "clean",
    sender_email: "investor.relations@fieldstoneequity.com",
    notice_text:
`From: investor.relations@fieldstoneequity.com
Subject: Fieldstone Equity Partners II - capital call due 2022-01-14

Hi Haas Group Retirement System team,

Quick capital call notice for Fieldstone Equity Partners II:

- Amount: $78,149.87
- Purpose: Capital call for follow-on investment in Grant Technologies
- Due: 2022-01-14
- Wire to: Meridian Trust Bank, routing 013710895, account 9280796110

Let us know if you have any questions.

Thanks,
Fieldstone Equity Management, LLC
`,
  },
  {
    key: "fraud-wrong-bank",
    label: "Fraud — wrong receiving bank",
    kind: "fraud",
    fraudType: "wrong_bank_valid_checksum",
    sender_email: "investor.relations@fieldstoneequity.com",
    notice_text:
`From: investor.relations@fieldstoneequity.com
Subject: URGENT - CAPITAL CALL Fieldstone Equity Partners II - PLEASE WIRE ASAP

hi Thomas-Avila Foundation,

need you to wire $113,627.47 by 2022-01-28 for capital call for follow-on investment in carpenter partners
this is for Fieldstone Equity Partners II.

bank is Redwood Capital Bank
routing 092614967
acct 9280796110

let me know once sent, thx
Fieldstone Equity Management, LLC
`,
  },
  {
    key: "fraud-spoofed-domain",
    label: "Fraud — look-alike sender domain",
    kind: "fraud",
    fraudType: "spoofed_sender_domain",
    sender_domain: "bl-ackfernventures.com",
    sender_email: "investor.relations@bl-ackfernventures.com",
    notice_text:
`From: capitalcalls@meridianfundadministration.com
Subject: Capital Call Notice - Blackfern Ventures Partners IV (Call #101)

This notice is being sent on behalf of Blackfern Ventures Management, LLC by Meridian Fund Administration,
fund administrator for Blackfern Ventures Partners IV.

Limited Partner: Owen-Robinson Pension Fund
Call Purpose: Capital call for follow-on investment in Jackson Industries
Call Amount Due: $815,153.35
Due Date: 2023-05-23

Wire Instructions:
Bank: Blue Harbor Bank & Trust
Routing #: 098588929
Account #: 993859245
Beneficiary: Blackfern Ventures Management, LLC

Please confirm receipt of this notice and remit funds by the due date.

Meridian Fund Administration
On behalf of Blackfern Ventures Partners IV
`,
  },
];
