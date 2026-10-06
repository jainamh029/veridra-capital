"""Four capital call notice styles, matching the range of formats GPs and
fund admins actually send: a formal letter-style PDF export, a casual bullet
email, a fund-administrator email, and a messy unstructured GP email.
"""


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def formal_pdf_style(ctx: dict) -> str:
    return f"""{ctx['gp_entity_name']}
CAPITAL CALL NOTICE #{ctx['call_number']}

Date: {ctx['call_date']}
To: {ctx['lp_name']}
Re: {ctx['fund_name']} — Capital Call

Dear Limited Partner,

Pursuant to the Limited Partnership Agreement of {ctx['fund_name']}, you are hereby
notified of a capital call in the amount set forth below.

  Fund:              {ctx['fund_name']}
  Purpose:           {ctx['purpose_description']}
  Call Amount:       {_money(ctx['amount'])}
  Due Date:          {ctx['due_date']}
  Payment Instructions:
    Bank Name:       {ctx['bank_name']}
    Routing Number:  {ctx['routing_number']}
    Account Number:  {ctx['account_number']}
    Account Name:    {ctx['gp_entity_name']}

Please remit the full amount by wire transfer no later than the due date above.
Questions may be directed to {ctx['contact_email']}.

Sincerely,
{ctx['gp_entity_name']}
Investor Relations
"""


def casual_bullet_email(ctx: dict) -> str:
    return f"""From: {ctx['sender_email']}
Subject: {ctx['fund_name']} - capital call due {ctx['due_date']}

Hi {ctx['lp_name']} team,

Quick capital call notice for {ctx['fund_name']}:

- Amount: {_money(ctx['amount'])}
- Purpose: {ctx['purpose_description']}
- Due: {ctx['due_date']}
- Wire to: {ctx['bank_name']}, routing {ctx['routing_number']}, account {ctx['account_number']}

Let us know if you have any questions.

Thanks,
{ctx['gp_entity_name']}
"""


def fund_admin_email(ctx: dict) -> str:
    return f"""From: capitalcalls@{ctx['admin_domain']}
Subject: Capital Call Notice - {ctx['fund_name']} (Call #{ctx['call_number']})

This notice is being sent on behalf of {ctx['gp_entity_name']} by {ctx['fund_admin_name']},
fund administrator for {ctx['fund_name']}.

Limited Partner: {ctx['lp_name']}
Call Purpose: {ctx['purpose_description']}
Call Amount Due: {_money(ctx['amount'])}
Due Date: {ctx['due_date']}

Wire Instructions:
Bank: {ctx['bank_name']}
Routing #: {ctx['routing_number']}
Account #: {ctx['account_number']}
Beneficiary: {ctx['gp_entity_name']}

Please confirm receipt of this notice and remit funds by the due date.

{ctx['fund_admin_name']}
On behalf of {ctx['fund_name']}
"""


def messy_gp_email(ctx: dict) -> str:
    return f"""From: {ctx['sender_email']}
Subject: URGENT - CAPITAL CALL {ctx['fund_name']} - PLEASE WIRE ASAP

hi {ctx['lp_name']},

need you to wire {_money(ctx['amount'])} by {ctx['due_date']} for {ctx['purpose_description'].lower()}
this is for {ctx['fund_name']}.

bank is {ctx['bank_name']}
routing {ctx['routing_number']}
acct {ctx['account_number']}

let me know once sent, thx
{ctx['gp_entity_name']}
"""


TEMPLATE_FUNCS = {
    "formal_pdf_style": formal_pdf_style,
    "casual_bullet_email": casual_bullet_email,
    "fund_admin_email": fund_admin_email,
    "messy_gp_email": messy_gp_email,
}


def render_notice(notice_format: str, ctx: dict) -> str:
    return TEMPLATE_FUNCS[notice_format](ctx)
