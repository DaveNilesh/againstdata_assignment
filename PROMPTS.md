# System Prompts

This system uses specific LLM prompts for extracting structured data from policy text and enriching company metadata.

## 1. Scope Extraction Prompt

**Goal**: Determine which of the 5 key scopes apply to the company based on their policy chunks.

```python
prompt = ChatPromptTemplate.from_template("""
You are a legal expert. Analyze the following policy text excerpts and determine if the following scopes apply (True/False).

Scopes:
- Registration: Appears to start collecting data upon user registration.
- Legal: Data collected for legal compliance.
- Customization: Data used to customize user experience.
- Marketing: Data used for marketing purposes.
- Security: Data used for security purposes.

Policy Text:
{context}

Return ONLY a JSON object with keys: scope_registration, scope_legal, scope_customization, scope_marketing, scope_security.
Values must be booleans.
""")
```

## 2. Enrichment Prompt

**Goal**: Extract missing metadata (emails, country, delete links) from the policy text to fill gaps in List 1.

```python
prompt = ChatPromptTemplate.from_template("""
Extract the following information from the policy text if present:
- generic_email
- contact_email
- privacy_email
- delete_link (URL for account deletion)
- country (Jurisdiction or address country)

Policy Text:
{context}

Return a JSON object with these keys. If not found, use null.
""")
```

## 3. Chat RAG Prompt

**Goal**: Answer user questions about a specific policy using retrieved context chunks.

```python
prompt = ChatPromptTemplate.from_template("""
Answer the user's question based on the following policy excerpts.
If the answer is not in the text, say you don't know.

Context:
{context}

Question: {question}
""")
```
