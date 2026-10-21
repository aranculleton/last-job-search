An invented LinkedIn data export for the example person (profile.example, Morgan Ellis), read
by tests/test_linkedin_export.py and tests/test_own_profile.py. Every name, address and message
is invented. The column names follow independent parsers of LinkedIn's export; they were not
checked against a file LinkedIn wrote.

- book_contacts.csv and book_threads.csv: the contact book and message log the history joins to.
- messages.csv: a thread with Juno Castellan whose first two messages the log already holds
  (addresses written as uk., ca. and www. variants); a reply from "Corwin Haldane, FIRP, GMS",
  who is in the book under his bare name with no address; a message from "Bob Smith" (the book
  has a Robert Smith) and one from another Wren Halloway at a different address, neither of whom may
  join; a group conversation.
- Invitations.csv: requests to a book contact (Tamsin Varga), a stranger (Quillon Varga), one
  too recent to list (Pell Ansgar), and one accepted since (Shirin Example, in Connections.csv).
- Profile.csv, Positions.csv, Education.csv, Skills.csv, Certifications.csv: a clean profile
  that agrees with profile.example in every checked part.
