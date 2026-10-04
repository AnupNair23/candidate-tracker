"""Identity, contact and work-authorization field detection used to keep sensitive data away from Claude."""

# Qualification names containing one of these hints describe work authorization / citizenship. They are only
# shown to Claude when the job has an authorization requirement.
AUTH_HINTS = ("authoriz", "citizen", "visa", "clearance", "itar", "work status", "workstatus", "legal")

# Normalized payload keys holding contact or identity data; never copied into candidate search text.
PII_KEYS = {
    "email",
    "emailaddress",
    "alternateemail",
    "candidateemail",
    "phone",
    "phone1",
    "phone2",
    "phone3",
    "phone4",
    "cellphone",
    "homephone",
    "workphone",
    "candidatephone",
    "candidatephones",
    "address",
    "address1",
    "address2",
    "candidateaddress",
    "firstname",
    "lastname",
    "candidatefirstname",
    "candidatelastname",
    "candidatename",
    "middleinitial",
    "dateofbirth",
    "dob",
    "ssn",
    "gender",
    "linkedin",
    "linkedinprofile",
}
