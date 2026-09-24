from .schema import (
    ComplianceValidationInput,
    ComplianceValidationResult,
    ConfidenceLevel,
    EvidenceEntry,
    ValidationStatus,
)


class ComplianceValidator:
    """Deterministic and extensible validation engine for generic documents and services."""

    def _add_evidence(
        self,
        evidence_list,
        source: str,
        requirement: str,
        evidence: str,
        result: ValidationStatus,
        next_action: str,
    ) -> None:
        evidence_list.append(
            EvidenceEntry(
                source=source,
                requirement=requirement,
                evidence=evidence,
                result=result,
                next_action=next_action,
            )
        )

    def _document_payload(self, value):
        if isinstance(value, dict):
            return value
        if value is True:
            return {"readable": True, "valid": True}
        if value is False or value in (None, "", {}):
            return None
        return {"value": value, "readable": True, "valid": True}

    def _normalized_documents(self, documents):
        normalized = {}
        for doc_name, doc_value in documents.items():
            payload = self._document_payload(doc_value)
            if payload is not None:
                normalized[doc_name] = payload
        return normalized

    def validate(
        self,
        data: ComplianceValidationInput,
    ) -> ComplianceValidationResult:
        requirements = data.requirements or {}

        service_type = requirements.get("service_type", data.service_type)
        document_type = requirements.get("document_type", data.document_type)
        document_type_name = (
            document_type.value
            if hasattr(document_type, "value")
            else str(document_type)
        )
        source = requirements.get("source", "Official requirement supplied by Information Retrieval Agent")

        missing_information = []
        missing_documents = []
        invalid_documents = []
        inconsistencies = []
        form_errors = []
        security_issues = []
        evidence = []
        confidence = dict(data.confidence)

        # 1. Validate required user information
        required_information = requirements.get("required_information", [])
        for field in required_information:
            value = data.user_information.get(field)
            if value is None or value == "":
                missing_information.append(field)
                self._add_evidence(
                    evidence,
                    source,
                    f"{field} is required for the {service_type} service.",
                    f"Required user information '{field}' is missing.",
                    ValidationStatus.WARNING,
                    "Ask the user to provide the missing information before continuing.",
                )
            else:
                confidence.setdefault(field, ConfidenceLevel.USER_CONFIRMED)

        # 2. Validate required documents generically
        required_documents = requirements.get("required_documents", [])
        all_documents = self._normalized_documents(data.documents)
        for document_name in required_documents:
            document_data = all_documents.get(document_name)
            if document_data is None:
                missing_documents.append(document_name)
                self._add_evidence(
                    evidence,
                    source,
                    f"{document_name} is required for the {service_type} service.",
                    f"Document '{document_name}' is missing or unusable.",
                    ValidationStatus.WARNING,
                    "Ask the user to upload the required document before continuing.",
                )
                continue

            readable = document_data.get("readable", True)
            valid = document_data.get("valid", True)
            expiry_valid = document_data.get("expiry_valid", True)

            if not readable:
                invalid_documents.append(document_name)
                self._add_evidence(
                    evidence,
                    source,
                    f"{document_name} must be readable and usable.",
                    f"Document '{document_name}' is unreadable or unusable.",
                    ValidationStatus.WARNING,
                    "Ask the user to re-upload a readable copy of the document.",
                )
            if not valid or not expiry_valid:
                invalid_documents.append(document_name)
                self._add_evidence(
                    evidence,
                    source,
                    f"{document_name} must be valid for the {service_type} service.",
                    f"Document '{document_name}' is expired, invalid, or unusable.",
                    ValidationStatus.BLOCKED,
                    "Stop the workflow and request a valid replacement document.",
                )
            if readable and valid and expiry_valid:
                self._add_evidence(
                    evidence,
                    source,
                    f"{document_name} satisfies the {service_type} requirements.",
                    f"Document '{document_name}' was provided and passes the generic document checks.",
                    ValidationStatus.PASS,
                    "Continue to the next validation step.",
                )

        # 3. Validate type-specific requirement metadata
        document_requirements = requirements.get("document_requirements", {})
        if isinstance(document_requirements, dict):
            for doc_name, rule_set in document_requirements.items():
                if doc_name not in all_documents:
                    continue
                required_fields = rule_set.get("required_fields", [])
                for field in required_fields:
                    if field not in all_documents[doc_name] or all_documents[doc_name].get(field) in (None, ""):
                        invalid_documents.append(doc_name)
                        self._add_evidence(
                            evidence,
                            source,
                            f"{doc_name} requires '{field}' to be present.",
                            f"Required field '{field}' is missing from document '{doc_name}'.",
                            ValidationStatus.WARNING,
                            "Ask the user to provide the missing document field before continuing.",
                        )

        # 4. Form validation
        required_form_fields = requirements.get("required_form_fields", [])
        for field in required_form_fields:
            value = data.form_data.get(field)
            if value is None or value == "":
                form_errors.append(f"Missing form field: {field}")
                self._add_evidence(
                    evidence,
                    source,
                    f"{field} is required in the application form for {service_type}.",
                    f"Form field '{field}' is empty or missing.",
                    ValidationStatus.WARNING,
                    "Ask the user to complete the missing field before continuing.",
                )

        # 5. Cross-check user, document, and form data
        all_fields = set(data.user_information) | set(data.form_data)
        for field in sorted(all_fields):
            user_value = data.user_information.get(field)
            form_value = data.form_data.get(field)
            if user_value is not None and form_value is not None and user_value != form_value:
                inconsistencies.append(f"{field} differs between user information and form data")
                self._add_evidence(
                    evidence,
                    source,
                    f"{field} must match the submitted application data.",
                    f"User value '{user_value}' does not match form value '{form_value}' for '{field}'.",
                    ValidationStatus.BLOCKED,
                    "Stop and ask the user to correct the conflicting information.",
                )

        document_values = {}
        for doc_name, payload in all_documents.items():
            for key in ["name", "date_of_birth", "address", "dob"]:
                if key in payload and payload.get(key) not in (None, ""):
                    document_values.setdefault(key, []).append(payload.get(key))

        for field in ["name", "date_of_birth", "address"]:
            user_value = data.user_information.get(field)
            if user_value is not None:
                field_values = document_values.get(field, [])
                if field_values and any(str(value) != str(user_value) for value in field_values):
                    inconsistencies.append(f"{field} differs between user information and one or more submitted documents")
                    self._add_evidence(
                        evidence,
                        source,
                        f"{field} must be consistent with the submitted document data.",
                        f"User value '{user_value}' differs from document values for '{field}'.",
                        ValidationStatus.BLOCKED,
                        "Stop and ask the user to resolve the conflicting identity information.",
                    )

        # 6. Security and privacy checks
        sensitive_action = requirements.get("sensitive_action", False)
        authorization_confirmed = requirements.get("authorization_confirmed", False)
        unverified_fields = [
            field
            for field, level in confidence.items()
            if level in (ConfidenceLevel.INFERRED, ConfidenceLevel.UNKNOWN)
        ]
        if sensitive_action and not authorization_confirmed:
            security_issues.append("Authorization is required before performing this sensitive action.")
            self._add_evidence(
                evidence,
                source,
                "Sensitive actions require explicit authorization before submission.",
                "High-impact action is requested without required user approval.",
                ValidationStatus.BLOCKED,
                "Stop the workflow and obtain explicit user authorization before continuing.",
            )
        if sensitive_action and unverified_fields:
            security_issues.append(
                "High-impact actions cannot rely on inferred or unknown information."
            )
            self._add_evidence(
                evidence,
                source,
                "High-impact actions require verified or user-confirmed information.",
                f"Unverified fields: {', '.join(unverified_fields)}.",
                ValidationStatus.BLOCKED,
                "Obtain verification or explicit user confirmation for the unverified fields.",
            )

        # 7. Confidence tracking
        for field in ["name", "date_of_birth", "address"]:
            if field in data.user_information and field not in confidence:
                confidence[field] = ConfidenceLevel.USER_CONFIRMED

        if inconsistencies or security_issues or invalid_documents:
            status = ValidationStatus.BLOCKED
        elif missing_information or missing_documents or form_errors:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASS

        if status == ValidationStatus.PASS:
            next_action = "All required validation checks passed. Continue to the next workflow step."
            self._add_evidence(
                evidence,
                source,
                "Final validation gate passed.",
                f"The submitted documents and information satisfy the official requirements for the {service_type} workflow.",
                ValidationStatus.PASS,
                "Continue to the next workflow step.",
            )
        elif status == ValidationStatus.WARNING:
            next_action = "Ask the user to provide the missing information or missing document before proceeding."
        else:
            next_action = "Stop the workflow and resolve the document inconsistency, invalid document, or authorization issue before continuing."

        return ComplianceValidationResult(
            document_type=document_type_name,
            service_type=str(service_type),
            status=status,
            overall_status=status,
            missing_information=missing_information,
            missing_documents=missing_documents,
            invalid_documents=invalid_documents,
            inconsistencies=inconsistencies,
            form_errors=form_errors,
            security_issues=security_issues,
            evidence=evidence,
            next_action=next_action,
            confidence=confidence,
        )