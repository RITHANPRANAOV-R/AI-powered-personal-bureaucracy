// HTTP success is transport delivery, not a verified portal outcome.
export function interpretExecutionStep(response, stageId) {
    const result = response?.execution_result;
    const known = ['VERIFIED_SUCCESS', 'FAILED', 'NEEDS_USER', 'BLOCKED', 'UNKNOWN'];
    const status = known.includes(result?.status) ? result.status : 'UNKNOWN';
    const verified = status === 'VERIFIED_SUCCESS'
        && response?.execution_uncertain !== true
        && response?.execution_diagnostic?.result_origin !== 'retained'
        && typeof result.message === 'string' && result.message.trim().length > 0
        && typeof result.verification_evidence === 'string'
        && result.verification_evidence.trim().length > 0
        && response.completed_stage === stageId;
    const final = response?.is_completed === true;
    const nextStage = {
        stage_1a_otp: 'stage_1b_login', stage_1b_login: 'stage_2_service',
        stage_2_service: 'stage_3_address', stage_3_address: 'stage_4_document',
        stage_4_document: 'stage_5_review',
    }[stageId];
    const validTransition = final
        ? response.current_stage === 'stage_6_completed'
            && stageId === 'stage_5_review'
            && typeof result?.official_reference === 'string'
            && result.official_reference.trim().length > 0
            && response.urn === result.official_reference
        : typeof response?.stage_info?.id === 'string'
            && response.current_stage === response.stage_info.id
            && response.current_stage === nextStage;
    return {
        completed: Boolean(verified && validTransition),
        final: Boolean(verified && validTransition && final),
        status: verified && validTransition ? status : (status === 'VERIFIED_SUCCESS' ? 'UNKNOWN' : status),
        message: typeof result?.message === 'string' && result.message.trim()
            ? result.message : 'The portal outcome has not been verified. This stage remains pending.',
    };
}
