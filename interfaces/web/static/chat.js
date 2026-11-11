
// ==========================

// CYN-X CHAT CLIENT

// ==========================



let timerInterval = null;

let startTime = null;

let lastResponseTime = 0;
let activePipelineRequestId = null;
let pipelineUsesTools = false;
let pipelineToolFailed = false;
let pipelineRequestRunning = false;
let pipelineFailureRecords = [];
let pipelineDismissTimeout = null;
let pipelineDismissInterval = null;
let pipelineDismissAt = 0;
let pipelineRemainingMs = 0;
let pipelineDismissPaused = false;
let pipelinePinned = false;
let pipelineReturnFocus = null;
const PIPELINE_SUCCESS_RETENTION_MS = 15000;
const PIPELINE_FAILURE_RETENTION_MS = 30000;
const PIPELINE_CANCEL_RETENTION_MS = 15000;

const toolSummaries = {
    web_search: "Searches current public web information.",
    calculator: "Evaluates the requested arithmetic.",
    filesystem: "Reads or lists project files.",
    smoke_counter: "Reads or updates the smoking tracker.",
    chart: "Builds a chart from the selected data.",
    lepro_lights: "Controls the selected Lepro lights."
};

const pipelineStageLabels = {
    request_received: "Request received",
    understanding: "Understanding request and context",
    evaluating_capabilities: "Evaluating available capabilities",
    decision: "Decision",
    tool_execution: "Tool execution",
    generating_response: "Generating response",
    completed: "Completed"
};

const pipelineStateLabels = {
    pending: "Pending",
    active: "In progress",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled"
};

const pipelineTools = new Map();





// ==========================

// PROMPT LAYERS

// ==========================



const promptLayerNames = [

    "core",

    "personality",

    "voice",

    "conversation",

    "safety",

    "modes",

    "examples",

    "overrides"

];





function getPromptLayers(){



    const layers = {};



    document

        .querySelectorAll(

            ".prompt-layer-checkbox"

        )

        .forEach(

            function(checkbox){



                const layer =

                    checkbox.dataset.layer;



                if(layer){

                    layers[layer] =

                        checkbox.checked;

                }



            }

        );



    return layers;

}





function setPromptLayers(layers){



    if(!layers)

        return;



    document

        .querySelectorAll(

            ".prompt-layer-checkbox"

        )

        .forEach(

            function(checkbox){



                const layer =

                    checkbox.dataset.layer;



                if(

                    layer &&

                    Object.prototype.hasOwnProperty.call(

                        layers,

                        layer

                    )

                ){



                    checkbox.checked =

                        Boolean(

                            layers[layer]

                        );

                }



            }

        );





    updatePromptLayerStatus();

}





function updatePromptLayerStatus(){



    const status =

        document.getElementById(

            "prompt-layer-status"

        );



    if(!status)

        return;



    const layers =

        getPromptLayers();



    const enabled =

        promptLayerNames.filter(

            function(layer){

                return layers[layer];

            }

        );



    if(

        enabled.length ===

        promptLayerNames.length

    ){



        status.innerText =

            "Full CYN";



        return;

    }





    if(enabled.length === 0){



        status.innerText =

            "No layers";



        return;

    }





    status.innerText =

        enabled.length +

        " layer" +

        (

            enabled.length === 1

                ? ""

                : "s"

        ) +

        " active";

}





function applyPromptPreset(preset){



    const presets = {



        base: {

            core: false,

            personality: false,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        core_only: {

            core: true,

            personality: false,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        core_safety: {

            core: true,

            personality: false,

            voice: false,

            conversation: false,

            safety: true,

            modes: false,

            examples: false,

            overrides: false

        },



        core_personality: {

            core: true,

            personality: true,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        full_cyn: {

            core: true,

            personality: true,

            voice: true,

            conversation: true,

            safety: true,

            modes: true,

            examples: true,

            overrides: true

        }

    };





    if(

        !Object.prototype.hasOwnProperty.call(

            presets,

            preset

        )

    ){

        return;

    }





    setPromptLayers(

        presets[preset]

    );

}





function detectPromptPreset(){



    const presetElement =

        document.getElementById(

            "prompt-preset"

        );



    if(!presetElement)

        return;



    const layers =

        getPromptLayers();



    const presets = {



        base: {

            core: false,

            personality: false,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        core_only: {

            core: true,

            personality: false,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        core_safety: {

            core: true,

            personality: false,

            voice: false,

            conversation: false,

            safety: true,

            modes: false,

            examples: false,

            overrides: false

        },



        core_personality: {

            core: true,

            personality: true,

            voice: false,

            conversation: false,

            safety: false,

            modes: false,

            examples: false,

            overrides: false

        },



        full_cyn: {

            core: true,

            personality: true,

            voice: true,

            conversation: true,

            safety: true,

            modes: true,

            examples: true,

            overrides: true

        }

    };





    for(

        const preset in presets

    ){



        const presetLayers =

            presets[preset];



        let matches = true;



        for(

            const layer of promptLayerNames

        ){



            if(

                Boolean(layers[layer])

                !==

                Boolean(presetLayers[layer])

            ){



                matches = false;

                break;

            }

        }





        if(matches){



            presetElement.value =

                preset;



            return;

        }



    }





    presetElement.value =

        "custom";

}





function initializePromptLayers(){



    const presetElement =

        document.getElementById(

            "prompt-preset"

        );



    const toggleButton =

        document.getElementById(

            "prompt-layers-toggle"

        );



    const content =

        document.getElementById(

            "prompt-layers-content"

        );



    const applyButton =

        document.getElementById(

            "apply-prompt-layers"

        );





    // --------------------------

    // Open / close panel

    // --------------------------



    if(

        toggleButton &&

        content

    ){



        toggleButton.addEventListener(

            "click",

            function(){



                content.hidden = !content.hidden;
                toggleButton.setAttribute("aria-expanded", String(!content.hidden));



            }

        );



    }





    // --------------------------

    // Preset selection

    // --------------------------



    if(presetElement){



        presetElement.addEventListener(

            "change",

            function(){



                if(

                    presetElement.value ===

                    "custom"

                ){



                    updatePromptLayerStatus();

                    return;

                }





                applyPromptPreset(

                    presetElement.value

                );



            }

        );



    }





    // --------------------------

    // Individual layer toggles

    // --------------------------



    document

        .querySelectorAll(

            ".prompt-layer-checkbox"

        )

        .forEach(

            function(checkbox){



                checkbox.addEventListener(

                    "change",

                    function(){



                        if(presetElement){



                            presetElement.value =

                                "custom";



                        }



                        updatePromptLayerStatus();



                    }

                );



            }

        );





    // --------------------------

    // Apply button

    // --------------------------



    if(applyButton){



        applyButton.addEventListener(

            "click",

            function(){



                detectPromptPreset();



                updatePromptLayerStatus();



                console.log(

                    "[PROMPT LAYERS] Applied:",

                    getPromptLayers()

                );



            }

        );



    }





    updatePromptLayerStatus();

}





// ==========================

// LOADING DISPLAY

// ==========================



function resetPipeline(){
    clearPipelineDismissTimers();
    pipelineTools.clear();
    pipelineUsesTools = false;
    pipelineToolFailed = false;
    pipelineFailureRecords = [];
    pipelineDismissPaused = false;
    pipelinePinned = false;
    pipelineRemainingMs = 0;

    document.querySelectorAll(".pipeline-stage").forEach((item) => {
        item.dataset.status = "pending";
        item.removeAttribute("aria-current");
        const label = item.querySelector(".stage-label");
        if(label) label.textContent = pipelineStageLabels[item.dataset.stage];
        const state = item.querySelector(".stage-state");
        if(state) state.textContent = pipelineStateLabels.pending;
        const detail = item.querySelector(".stage-detail");
        const time = item.querySelector(".stage-time");
        if(detail) detail.textContent = "";
        if(time){
            time.textContent = "";
            time.removeAttribute("datetime");
        }
    });

    const tools = document.getElementById("pipeline-tools");
    if(tools) tools.replaceChildren();
    const status = document.getElementById("pipeline-status");
    if(status) status.textContent = "Waiting for request events";
    const viewState = document.getElementById("pipeline-view-state");
    if(viewState) viewState.textContent = "LIVE REQUEST TRACE";
    const cancelButton = document.getElementById("pipeline-cancel");
    if(cancelButton) cancelButton.disabled = true;
    const keepOpen = document.getElementById("pipeline-keep-open");
    if(keepOpen){
        keepOpen.hidden = true;
        keepOpen.setAttribute("aria-pressed", "false");
        keepOpen.textContent = "Keep open";
    }
    const resume = document.getElementById("pipeline-resume");
    if(resume) resume.hidden = true;
    const dismiss = document.getElementById("pipeline-dismiss");
    if(dismiss) dismiss.hidden = true;
    const outcome = document.getElementById("pipeline-outcome");
    if(outcome){
        outcome.hidden = true;
        outcome.removeAttribute("data-kind");
    }
    const details = document.getElementById("pipeline-failure-details");
    if(details){
        details.hidden = true;
        details.open = false;
    }
    const failureList = document.getElementById("pipeline-failure-list");
    if(failureList) failureList.replaceChildren();
    const title = document.getElementById("pipeline-outcome-title");
    if(title) title.textContent = "";
    const message = document.getElementById("pipeline-outcome-message");
    if(message) message.textContent = "";
    const retention = document.getElementById("pipeline-retention-message");
    if(retention) retention.textContent = "";
}

function setPipelineStage(stage, status, event){
    const item = document.querySelector(
        `.pipeline-stage[data-stage="${stage}"]`
    );
    if(!item) return;

    item.dataset.status = status;
    document.querySelectorAll(".pipeline-stage[aria-current]").forEach((active) => {
        active.removeAttribute("aria-current");
    });
    if(status === "active") item.setAttribute("aria-current", "step");

    const state = item.querySelector(".stage-state");
    if(state) state.textContent = pipelineStateLabels[status] || status;
    if(event && event.timestamp){
        const time = item.querySelector(".stage-time");
        if(time){
            time.dateTime = event.timestamp;
            time.textContent = Number.isFinite(event.elapsed_seconds)
                ? `T+${Number(event.elapsed_seconds).toFixed(1)}s`
                : "";
        }
    }

    const statusText = document.getElementById("pipeline-status");
    if(statusText && status === "active"){
        const label = item.querySelector(".stage-label");
        statusText.textContent = label ? label.textContent : "CYN-X Core is working";
    }
}

function renderPipelineTools(){
    const list = document.getElementById("pipeline-tools");
    if(!list) return;
    list.replaceChildren();

    for(const [id, tool] of pipelineTools){
        const item = document.createElement("li");
        item.className = "pipeline-tool";
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        const explanation = toolSummaries[tool.name]
            || `CYN-X selected the ${tool.name} tool for this request.`;
        summary.textContent = `${tool.name} — ${tool.status}: ${explanation}`;
        details.appendChild(summary);

        const timing = document.createElement("p");
        if(tool.startedAt){
            const started = new Date(tool.startedAt);
            timing.textContent = `Started ${started.toLocaleTimeString()}`;
            if(tool.completedAt){
                const completed = new Date(tool.completedAt);
                const duration = Math.max(
                    0,
                    tool.completedElapsed - tool.startedElapsed
                ).toFixed(2);
                timing.textContent += ` · completed ${completed.toLocaleTimeString()} (${duration}s)`;
            }
        }
        details.appendChild(timing);
        item.dataset.invocationId = id;
        item.dataset.status = tool.status.toLowerCase();
        item.appendChild(details);
        list.appendChild(item);
    }
}

function recordPipelineFailure(record){
    const identity = record.invocationId || `${record.stage || "request"}:${record.tool || ""}`;
    if(pipelineFailureRecords.some((existing) => existing.identity === identity)) return;
    pipelineFailureRecords.push({...record, identity});
}

function renderPipelineFailureDetails(){
    const details = document.getElementById("pipeline-failure-details");
    const list = document.getElementById("pipeline-failure-list");
    if(!details || !list) return;
    list.replaceChildren();

    for(const failure of pipelineFailureRecords){
        const item = document.createElement("li");
        const stageName = pipelineStageLabels[failure.stage] || "Request processing";
        const toolLabel = failure.tool ? ` · Tool: ${failure.tool}` : "";
        const reason = failure.tool
            ? `The ${failure.tool} tool reported that it could not complete this step.`
            : "This part of the request could not finish.";
        const retry = typeof failure.retryable === "boolean"
            ? (failure.retryable ? " Retry may be possible." : " This operation is not marked as retryable.")
            : " Retry availability was not reported.";
        item.textContent = `${stageName}${toolLabel} — ${reason}${retry}`;
        list.appendChild(item);
    }
    details.hidden = pipelineFailureRecords.length === 0;
}

function handlePipelineEvent(event, requestId){
    if(requestId !== activePipelineRequestId || !pipelineRequestRunning) return;

    if(event.type === "stage"){
        setPipelineStage(event.stage, event.status, event);
        if(event.status === "failed"){
            pipelineToolFailed = event.stage === "tool_execution" || pipelineToolFailed;
            recordPipelineFailure({
                stage: event.stage,
                retryable: typeof event.retryable === "boolean" ? event.retryable : undefined
            });
        }
        if(event.stage === "generating_response" && pipelineUsesTools){
            const activeTool = Array.from(pipelineTools.values()).some(
                (tool) => tool.status === "started"
            );
            if(!activeTool){
                setPipelineStage(
                    "tool_execution",
                    pipelineToolFailed ? "failed" : "completed",
                    event
                );
            }
        }
        if(event.stage === "request_received" && event.status === "completed"){
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = "Request received by CYN-X Core";
            const cancelButton = document.getElementById("pipeline-cancel");
            if(cancelButton) cancelButton.disabled = false;
        }
        return;
    }

    if(event.type === "decision"){
        setPipelineStage("decision", "completed", event);
        const item = document.querySelector('.pipeline-stage[data-stage="decision"]');
        const detail = item && item.querySelector(".stage-detail");
        const names = Array.isArray(event.tools) ? event.tools.filter(Boolean) : [];
        pipelineUsesTools = event.action === "use_tools" && names.length > 0;
        if(detail){
            detail.textContent = pipelineUsesTools
                ? `Selected: ${names.join(", ")}`
                : "Answering directly; no tool selected.";
        }
        if(!pipelineUsesTools){
            setPipelineStage("tool_execution", "completed", event);
            const toolDetail = document.querySelector(
                '.pipeline-stage[data-stage="tool_execution"] .stage-detail'
            );
            if(toolDetail) toolDetail.textContent = "Not needed for this request.";
        }
        return;
    }

    if(event.type === "tool"){
        const id = event.invocation_id || `${event.name}-${event.id}`;
        pipelineTools.set(id, {
            name: event.name,
            status: event.status,
            timestamp: event.timestamp,
            startedAt: event.status === "started"
                ? event.timestamp
                : (pipelineTools.get(id) || {}).startedAt,
            completedAt: event.status !== "started"
                ? event.timestamp
                : (pipelineTools.get(id) || {}).completedAt,
            startedElapsed: event.status === "started"
                ? event.elapsed_seconds
                : (pipelineTools.get(id) || {}).startedElapsed,
            completedElapsed: event.status !== "started"
                ? event.elapsed_seconds
                : (pipelineTools.get(id) || {}).completedElapsed
        });
        if(event.status === "failed"){
            pipelineToolFailed = true;
            recordPipelineFailure({
                stage: "tool_execution",
                tool: event.name,
                invocationId: id,
                retryable: typeof event.retryable === "boolean" ? event.retryable : undefined
            });
        }
        renderPipelineTools();
        if(event.status === "started"){
            setPipelineStage("tool_execution", "active", event);
        }else if(event.status === "failed"){
            setPipelineStage("tool_execution", "failed", event);
        }
        return;
    }

    if(event.type === "request_completed"){
        setPipelineStage("completed", "completed", event);
        finishPipeline(pipelineFailureRecords.length ? "partial" : "success", requestId);
        return;
    }

    if(event.type === "cancel_requested"){
        const status = document.getElementById("pipeline-status");
        if(status){
            status.textContent = "Cancellation requested. CYN-X will stop at the next safe point.";
        }
        const cancelButton = document.getElementById("pipeline-cancel");
        if(cancelButton) cancelButton.disabled = true;
        return;
    }

    if(event.type === "request_cancelled"){
        document.querySelectorAll('.pipeline-stage[data-status="active"]').forEach(
            (active) => setPipelineStage(active.dataset.stage, "cancelled", event)
        );
        const finalLabel = document.querySelector('.pipeline-stage[data-stage="completed"] .stage-label');
        if(finalLabel) finalLabel.textContent = "Request cancelled";
        setPipelineStage("completed", "cancelled", event);
        finishPipeline("cancelled", requestId);
        return;
    }

    if(event.type === "request_failed"){
        const activeStages = Array.from(
            document.querySelectorAll('.pipeline-stage[data-status="active"]')
        );
        if(activeStages.length){
            activeStages.forEach((active) => {
                recordPipelineFailure({stage: active.dataset.stage});
                setPipelineStage(active.dataset.stage, "failed", event);
            });
        }
        if(!pipelineFailureRecords.length){
            recordPipelineFailure({stage: "completed"});
        }
        const finalLabel = document.querySelector('.pipeline-stage[data-stage="completed"] .stage-label');
        if(finalLabel) finalLabel.textContent = "Request failed";
        setPipelineStage("completed", "failed", event);
        finishPipeline("failure", requestId);
    }
}

function clearPipelineDismissTimers(){
    if(pipelineDismissTimeout) clearTimeout(pipelineDismissTimeout);
    if(pipelineDismissInterval) clearInterval(pipelineDismissInterval);
    pipelineDismissTimeout = null;
    pipelineDismissInterval = null;
    pipelineDismissAt = 0;
}

function updatePipelineRetentionMessage(){
    const message = document.getElementById("pipeline-retention-message");
    const resume = document.getElementById("pipeline-resume");
    if(!message) return;
    if(pipelineRequestRunning){
        message.textContent = "This request is still running.";
        if(resume) resume.hidden = true;
    }else if(pipelinePinned){
        message.textContent = "Kept open until you dismiss it.";
        if(resume) resume.hidden = true;
    }else if(pipelineDismissPaused){
        message.textContent = "Auto-close paused while you read. Resume it or dismiss this panel.";
        if(resume) resume.hidden = false;
    }else if(pipelineDismissAt){
        const seconds = Math.max(0, Math.ceil((pipelineDismissAt - Date.now()) / 1000));
        message.textContent = `This previous request will close in ${seconds} seconds.`;
        if(resume) resume.hidden = true;
    }
}

function schedulePipelineDismiss(delayMs){
    clearPipelineDismissTimers();
    if(pipelineRequestRunning || pipelinePinned || pipelineDismissPaused) return;
    pipelineRemainingMs = Math.max(0, delayMs);
    pipelineDismissAt = Date.now() + pipelineRemainingMs;
    updatePipelineRetentionMessage();
    pipelineDismissTimeout = setTimeout(() => dismissPipeline(), pipelineRemainingMs);
    pipelineDismissInterval = setInterval(updatePipelineRetentionMessage, 250);
}

function pausePipelineAutoDismiss(){
    if(pipelineRequestRunning || pipelinePinned || pipelineDismissPaused || !pipelineDismissAt) return;
    pipelineRemainingMs = Math.max(0, pipelineDismissAt - Date.now());
    pipelineDismissPaused = true;
    clearPipelineDismissTimers();
    updatePipelineRetentionMessage();
}

function resumePipelineAutoDismiss(){
    if(pipelineRequestRunning || pipelinePinned) return;
    pipelineDismissPaused = false;
    if(pipelineRemainingMs <= 0){
        dismissPipeline();
        return;
    }
    schedulePipelineDismiss(pipelineRemainingMs);
}

function togglePipelineKeepOpen(){
    const button = document.getElementById("pipeline-keep-open");
    if(!button || pipelineRequestRunning) return;
    pipelinePinned = !pipelinePinned;
    button.setAttribute("aria-pressed", String(pipelinePinned));
    button.textContent = pipelinePinned ? "Unpin panel" : "Keep open";
    if(pipelinePinned){
        pipelineRemainingMs = pipelineDismissAt
            ? Math.max(0, pipelineDismissAt - Date.now())
            : pipelineRemainingMs;
        clearPipelineDismissTimers();
        pipelineDismissPaused = false;
        updatePipelineRetentionMessage();
    }else{
        pipelineDismissPaused = false;
        schedulePipelineDismiss(pipelineRemainingMs || PIPELINE_SUCCESS_RETENTION_MS);
    }
}

function dismissPipeline(){
    if(pipelineRequestRunning) return;
    clearPipelineDismissTimers();
    const panel = document.getElementById("thinking");
    if(panel){
        panel.style.display = "none";
        panel.setAttribute("aria-hidden", "true");
    }
    pipelinePinned = false;
    pipelineDismissPaused = false;
    if(pipelineReturnFocus && typeof pipelineReturnFocus.focus === "function"){
        pipelineReturnFocus.focus();
    }
}

function finishPipeline(outcome, requestId){
    if(requestId !== activePipelineRequestId || !pipelineRequestRunning) return;
    pipelineRequestRunning = false;
    const panelElement = document.getElementById("thinking");
    if(panelElement) panelElement.setAttribute("aria-busy", "false");
    clearInterval(timerInterval);
    if(startTime){
        updateTimer();
        lastResponseTime = (performance.now() - startTime) / 1000;
        updateResponseTime();
    }

    const cancelButton = document.getElementById("pipeline-cancel");
    if(cancelButton) cancelButton.disabled = true;
    const dismiss = document.getElementById("pipeline-dismiss");
    if(dismiss) dismiss.hidden = false;
    const keepOpen = document.getElementById("pipeline-keep-open");
    if(keepOpen) keepOpen.hidden = false;
    const viewState = document.getElementById("pipeline-view-state");
    if(viewState){
        viewState.textContent = outcome === "failure"
            ? "PREVIOUS REQUEST · FAILED"
            : outcome === "cancelled"
                ? "PREVIOUS REQUEST · CANCELLED"
                : outcome === "partial"
                    ? "PREVIOUS REQUEST · PARTIAL RESULTS"
                    : "PREVIOUS REQUEST · COMPLETED";
    }

    const panel = document.getElementById("pipeline-outcome");
    const title = document.getElementById("pipeline-outcome-title");
    const message = document.getElementById("pipeline-outcome-message");
    const status = document.getElementById("pipeline-status");
    if(panel){
        panel.hidden = false;
        panel.dataset.kind = outcome;
    }
    if(outcome === "success"){
        if(title) title.textContent = "Completed successfully";
        if(message) message.textContent = "CYN-X finished the request and generated a response.";
        if(status) status.textContent = "Request completed successfully.";
    }else if(outcome === "partial"){
        if(title) title.textContent = "Completed with partial results";
        if(message) message.textContent = "CYN-X returned a response, but one or more tools failed. Some results may be incomplete.";
        if(status) status.textContent = "Request completed with partial results.";
    }else if(outcome === "cancelled"){
        if(title) title.textContent = "Request cancelled";
        if(message) message.textContent = "CYN-X stopped this request. It was not treated as a failure.";
        if(status) status.textContent = "Request was cancelled.";
    }else{
        if(title) title.textContent = "Request could not be completed";
        if(message) message.textContent = "CYN-X couldn't finish this request. Inspect the details to see which stage or tool stopped.";
        if(status) status.textContent = "Request failed before a response was ready.";
    }
    renderPipelineFailureDetails();

    pipelineDismissPaused = false;
    pipelinePinned = false;
    if(keepOpen){
        keepOpen.setAttribute("aria-pressed", "false");
        keepOpen.textContent = "Keep open";
    }
    const retentionMs = outcome === "failure" || outcome === "partial"
        ? PIPELINE_FAILURE_RETENTION_MS
        : outcome === "cancelled"
            ? PIPELINE_CANCEL_RETENTION_MS
            : PIPELINE_SUCCESS_RETENTION_MS;
    pipelineRemainingMs = retentionMs;
    schedulePipelineDismiss(retentionMs);
}

function markPipelineRequestFailed(requestId){
    if(requestId !== activePipelineRequestId || !pipelineRequestRunning) return;
    const activeStages = Array.from(
        document.querySelectorAll('.pipeline-stage[data-status="active"]')
    );
    activeStages.forEach((active) => {
        recordPipelineFailure({stage: active.dataset.stage});
        setPipelineStage(active.dataset.stage, "failed");
    });
    if(!pipelineFailureRecords.length) recordPipelineFailure({stage: null});
    const finalLabel = document.querySelector('.pipeline-stage[data-stage="completed"] .stage-label');
    if(finalLabel) finalLabel.textContent = "Request failed";
    setPipelineStage("completed", "failed");
    finishPipeline("failure", requestId);
}

async function watchPipelineEvents(requestId, signal){
    let cursor = 0;
    while(!signal.aborted){
        const response = await fetch(
            `/chat/events/${encodeURIComponent(requestId)}?after=${cursor}`,
            {signal}
        );
        if(!response.ok) throw new Error("Could not read request events.");

        const data = await response.json();
        for(const event of data.events || []){
            cursor = Math.max(cursor, event.id);
            if(requestId === activePipelineRequestId){
                handlePipelineEvent(event, requestId);
            }
        }
        if(data.done) return true;
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return false;
}

function startLoading(requestId){
    const panel = document.getElementById("thinking");
    if(panel){
        panel.style.display = "flex";
    }
    activePipelineRequestId = requestId;
    pipelineRequestRunning = true;
    resetPipeline();
    if(panel){
        panel.removeAttribute("aria-hidden");
        panel.setAttribute("aria-busy", "true");
    }
    startTime = performance.now();
    clearInterval(timerInterval);
    updateTimer();
    timerInterval = setInterval(updateTimer, 100);
}

function stopLoading(requestId){
    if(requestId !== activePipelineRequestId) return;
    if(startTime){
        clearInterval(timerInterval);
        lastResponseTime = (performance.now() - startTime) / 1000;
        updateResponseTime();
    }
}

async function cancelActiveRequest(){
    const requestId = activePipelineRequestId;
    if(!requestId || !pipelineRequestRunning) return;

    const cancelButton = document.getElementById("pipeline-cancel");
    if(cancelButton) cancelButton.disabled = true;

    try{
        const response = await fetch(
            `/chat/cancel/${encodeURIComponent(requestId)}`,
            {method: "POST"}
        );
        if(!response.ok) throw new Error("Could not request cancellation.");
        const result = await response.json();
        if(!result.requested && requestId === activePipelineRequestId){
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = "This request has already finished.";
            if(cancelButton) cancelButton.disabled = true;
        }
    }catch(_error){
        if(requestId === activePipelineRequestId && pipelineRequestRunning){
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = "CYN-X could not confirm the cancellation request.";
            if(cancelButton) cancelButton.disabled = false;
        }
    }
}

function updateTimer(){



    if(!startTime)

        return;





    const timer =

        document.getElementById(

            "timer"

        );





    if(timer){



        let seconds =

            (

                performance.now()

                -

                startTime

            )

            /

            1000;





        timer.innerText =

            seconds.toFixed(1);

    }



}









function updateResponseTime(){



    const display =

        document.getElementById(

            "response-time"

        );





    if(display){



        display.innerText =

            "Last Response: "

            +

            lastResponseTime.toFixed(2)

            +

            " seconds";



    }



}













// ==========================

// CHAT

// ==========================



async function send(){
    const input = document.getElementById("message");
    const text = input.value.trim();
    if(!text || pipelineRequestRunning) return;

    addMessage("You: " + text);
    input.value = "";

    const requestId = window.crypto && window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const eventController = new AbortController();
    startLoading(requestId);
    if(window.CynxShell) window.CynxShell.setRequestBusy(true);
    const generationStatus = document.getElementById("generation-status");
    if(generationStatus) generationStatus.hidden = false;
    const pipelinePromise = watchPipelineEvents(requestId, eventController.signal)
        .catch(() => {
            if(requestId === activePipelineRequestId && pipelineRequestRunning){
                const status = document.getElementById("pipeline-status");
                if(status) status.textContent = "Live updates paused; waiting for the request result.";
            }
            return false;
        });

    try{
        const response = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                message: text,
                prompt_layers: getPromptLayers(),
                request_id: requestId,
                conversation_id: window.CynxShell ? window.CynxShell.conversationId() : undefined
            })
        });
        let data = {};
        try { data = await response.json(); } catch(_error) { data = {}; }

        await pipelinePromise;
        if(!response.ok){
            if(pipelineRequestRunning && requestId === activePipelineRequestId){
                markPipelineRequestFailed(requestId);
            }
            throw new Error("CYN-X couldn't complete this request. See the pipeline for details.");
        }

        if(data.cancelled){
            addMessage("[Request cancelled.]");
            if(requestId === activePipelineRequestId && pipelineRequestRunning){
                const finalLabel = document.querySelector('.pipeline-stage[data-stage="completed"] .stage-label');
                if(finalLabel) finalLabel.textContent = "Request cancelled";
                setPipelineStage("completed", "cancelled");
                finishPipeline("cancelled", requestId);
            }
            stopLoading(requestId);
            return;
        }

        if(requestId === activePipelineRequestId && pipelineRequestRunning){
            setPipelineStage("completed", "completed");
            finishPipeline(pipelineFailureRecords.length ? "partial" : "success", requestId);
        }

        if(data.prompt_layers){
            setPromptLayers(data.prompt_layers);
            detectPromptPreset();
        }

        const cynResponse = data.response;
        if(cynResponse && typeof cynResponse === "object"){
            addMessage("Cyn: " + (cynResponse.text || ""));
            if(cynResponse.chart) addChart(cynResponse.chart);
        }else{
            addMessage("Cyn: " + (cynResponse || ""));
        }
        stopLoading(requestId);
    }catch(_error){
        await pipelinePromise;
        if(pipelineRequestRunning && requestId === activePipelineRequestId){
            markPipelineRequestFailed(requestId);
        }
        eventController.abort();
        stopLoading(requestId);
        addMessage("[ERROR] CYN-X couldn't complete this request. See the request pipeline for details.");
    }finally{
        eventController.abort();
        if(window.CynxShell) window.CynxShell.setRequestBusy(false);
        if(generationStatus) generationStatus.hidden = true;
    }
}

// CHAT DISPLAY

// ==========================



function escapeHTML(text){

    const div = document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}



function formatCynText(text){

    // If marked and DOMPurify are available, render Markdown -> sanitize -> return.

    if (

        typeof marked !== 'undefined' &&

        typeof DOMPurify !== 'undefined'

    ) {



        const renderer =

            new marked.Renderer();



        // Render links only for http/https and add the required attributes

        renderer.link = function(

            href,

            title,

            text

        ) {



            try {



                if (!href)

                    return escapeHTML(text);



                // allow only http(s)

                if (

                    !/^https?:\/\//i.test(

                        href

                    )

                ) {



                    return escapeHTML(

                        text

                    );

                }



                const safeHref =

                    escapeHTML(

                        href

                    );



                const safeText =

                    text || safeHref;



                const titleAttr =

                    title

                        ? ' title="' +

                          escapeHTML(

                              title

                          ) +

                          '"'

                        : '';



                return (

                    '<a class="cyn-link" href="' +

                    safeHref +

                    '"' +

                    titleAttr +

                    ' target="_blank" rel="noopener noreferrer">' +

                    safeText +

                    '</a>'

                );



            }



            catch (e) {



                return escapeHTML(

                    text

                );

            }



        };



        // Escape any raw HTML blocks from the model to avoid injecting HTML

        renderer.html = function(

            html

        ) {



            return escapeHTML(

                html

            );



        };



        const rawHtml =

            marked.parse(

                text,

                {

                    renderer:

                        renderer

                }

            );



        // Sanitize produced HTML and only allow http/https URIs

        const clean =

            DOMPurify.sanitize(

                rawHtml,

                {

                    ALLOWED_URI_REGEXP:

                        /^https?:/i

                }

            );



        return clean;

    }



    // Fallback: escape and linkify as before

    let safeText =

        escapeHTML(

            text

        );



    safeText =

        safeText.replace(

            /(https?:\/\/[^\s<]+)/gi,

            function(url){



                // Remove punctuation accidentally attached to URL.

                let cleanURL = url;

                let trailing = "";



                const match =

                    url.match(

                        /[.,!?;:)]+$/

                    );



                if(match){



                    trailing =

                        match[0];



                    cleanURL =

                        url.substring(

                            0,

                            url.length -

                            trailing.length

                        );



                }



                return (

                    '<a class="cyn-link" ' +

                    'href="' +

                    cleanURL +

                    '" ' +

                    'target="_blank" ' +

                    'rel="noopener noreferrer">' +

                    cleanURL +

                    '</a>' +

                    trailing

                );



            }

        );



    // Preserve line breaks in Cyn responses.

    safeText =

        safeText.replace(

            /\n/g,

            "<br>"

        );



    return safeText;

}



function addMessage(message) {

    const chat = document.getElementById("chat");

    if (!chat)

        return;

    const div = document.createElement("div");

    div.className = "message";

    if (message.startsWith("You:")) {
        div.dataset.role = "user";

        const text = message.substring(4);

        div.innerHTML =

            '<span class="you-name">You:</span>' +

            '<span class="you-text">' +

            escapeHTML(text) +

            '</span>';

    }

    else if (message.startsWith("Cyn:")) {
        div.dataset.role = "assistant";

        const text = message.substring(4);

        div.innerHTML =

            '<span class="cyn-name">Cyn:</span>' +

            '<span class="cyn-text">' +

            formatCynText(text) +

            '</span>';

    }

    else {

        div.textContent = message;

    }

    chat.appendChild(div);

    chat.scrollTop = chat.scrollHeight;
    if(window.CynxShell) window.CynxShell.recordMessage(message);

}





// ==========================

// KEYBOARD SUPPORT

// ==========================



window.onload = function(){



    initializePromptLayers();

    const cancelButton = document.getElementById("pipeline-cancel");
    if(cancelButton){
        cancelButton.addEventListener("click", cancelActiveRequest);
    }

    const keepOpenButton = document.getElementById("pipeline-keep-open");
    if(keepOpenButton) keepOpenButton.addEventListener("click", togglePipelineKeepOpen);
    const resumeButton = document.getElementById("pipeline-resume");
    if(resumeButton) resumeButton.addEventListener("click", resumePipelineAutoDismiss);
    const dismissButton = document.getElementById("pipeline-dismiss");
    if(dismissButton) dismissButton.addEventListener("click", dismissPipeline);

    const pipelinePanel = document.getElementById("thinking");
    if(pipelinePanel){
        pipelinePanel.addEventListener("pointerdown", pausePipelineAutoDismiss);
        pipelinePanel.addEventListener("wheel", pausePipelineAutoDismiss, {passive: true});
        pipelinePanel.addEventListener("focusin", (event) => {
            if(!pipelinePanel.contains(event.relatedTarget) && event.relatedTarget instanceof HTMLElement){
                pipelineReturnFocus = event.relatedTarget;
            }
            pausePipelineAutoDismiss();
        });
        pipelinePanel.addEventListener("keydown", (event) => {
            pausePipelineAutoDismiss();
            if(event.key === "Escape" && !pipelineRequestRunning){
                event.preventDefault();
                dismissPipeline();
            }
        });
    }





    const input =

        document.getElementById(

            "message"

        );





    if(input){



        input.addEventListener(

            "keydown",

            function(event){



                if(event.key === "Enter" && !event.shiftKey && !event.isComposing){
                    event.preventDefault();
                    send();
                }



            }

        );



    }



};













// ==========================

// OPTIONAL DEBUG

// ==========================



console.log(

    "CYN-X chat interface loaded"

);

document.addEventListener(

    "DOMContentLoaded",

    () => {



        console.log(

            "CYN-X DOM READY"

        );



        initializePromptLayers();





        const button =

            document.getElementById(

                "sendButton"

            );



        if(button){

            button.addEventListener(

                "click",

                send

            );



            console.log(

                "SEND BUTTON CONNECTED"

            );

        }

        else{

            console.error(

                "SEND BUTTON NOT FOUND"

            );

        }



    }

);
