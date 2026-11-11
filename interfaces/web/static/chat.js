
// ==========================

// CYN-X CHAT CLIENT

// ==========================



let timerInterval = null;

let startTime = null;

let lastResponseTime = 0;
let activePipelineRequestId = null;

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



                if(

                    content.style.display ===

                    "none"

                ){



                    content.style.display =

                        "block";



                }

                else{



                    content.style.display =

                        "none";



                }



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
    pipelineTools.clear();
    document.querySelectorAll(".pipeline-stage").forEach((item) => {
        item.dataset.status = "waiting";
        const label = item.querySelector(".stage-label");
        if(label) label.textContent = pipelineStageLabels[item.dataset.stage];
        const detail = item.querySelector(".stage-detail");
        const time = item.querySelector(".stage-time");
        if(detail) detail.textContent = "";
        if(time) time.textContent = "";
    });
    const tools = document.getElementById("pipeline-tools");
    if(tools) tools.replaceChildren();
    const status = document.getElementById("pipeline-status");
    if(status) status.textContent = "Waiting for request events";
    const cancelButton = document.getElementById("pipeline-cancel");
    if(cancelButton) cancelButton.disabled = true;
}

function setPipelineStage(stage, status, event){
    const item = document.querySelector(
        `.pipeline-stage[data-stage="${stage}"]`
    );
    if(!item) return;

    item.dataset.status = status;
    if(event && event.timestamp){
        const time = item.querySelector(".stage-time");
        if(time){
            const date = new Date(event.timestamp);
            time.dateTime = date.toISOString();
            time.textContent = date.toLocaleTimeString();
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

function handlePipelineEvent(event){
    if(event.type === "stage"){
        setPipelineStage(event.stage, event.status, event);
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
        if(detail){
            detail.textContent = event.action === "use_tools" && names.length
                ? `Using ${names.join(", ")}`
                : "Answering directly; no tool selected.";
        }
        if(event.action !== "use_tools" || names.length === 0){
            setPipelineStage("tool_execution", "completed", event);
            const toolStage = document.querySelector(
                '.pipeline-stage[data-stage="tool_execution"] .stage-label'
            );
            if(toolStage) toolStage.textContent = "Tool execution — not needed";
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
        renderPipelineTools();
        if(event.status === "started"){
            setPipelineStage("tool_execution", "active", event);
        }else if(event.status === "failed"){
            setPipelineStage("tool_execution", "failed", event);
        }else if(!Array.from(pipelineTools.values()).some(
            (tool) => tool.status === "started"
        )){
            setPipelineStage("tool_execution", "completed", event);
        }
        return;
    }

    if(event.type === "request_completed"){
        setPipelineStage("completed", "completed", event);
        const status = document.getElementById("pipeline-status");
        if(status) status.textContent = "CYN-X Core completed the request";
        const cancelButton = document.getElementById("pipeline-cancel");
        if(cancelButton) cancelButton.disabled = true;
        return;
    }

    if(event.type === "cancel_requested"){
        const status = document.getElementById("pipeline-status");
        if(status){
            status.textContent =
                "Cancellation requested; the current Core or tool operation must finish first.";
        }
        const cancelButton = document.getElementById("pipeline-cancel");
        if(cancelButton) cancelButton.disabled = true;
        return;
    }

    if(event.type === "request_cancelled"){
        document.querySelectorAll('.pipeline-stage[data-status="active"]').forEach(
            (active) => active.dataset.status = "failed"
        );
        setPipelineStage("completed", "failed", event);
        const status = document.getElementById("pipeline-status");
        if(status) status.textContent = event.message || "Request cancelled.";
        const cancelButton = document.getElementById("pipeline-cancel");
        if(cancelButton) cancelButton.disabled = true;
        return;
    }

    if(event.type === "request_failed"){
        document.querySelectorAll('.pipeline-stage[data-status="active"]').forEach(
            (active) => active.dataset.status = "failed"
        );
        setPipelineStage("completed", "failed", event);
        const status = document.getElementById("pipeline-status");
        if(status) status.textContent = event.message || "CYN-X Core could not complete this request.";
        const cancelButton = document.getElementById("pipeline-cancel");
        if(cancelButton) cancelButton.disabled = true;
    }
}

async function watchPipelineEvents(requestId, signal){
    let cursor = 0;
    while(!signal.aborted){
        const response = await fetch(
            `/chat/events/${encodeURIComponent(requestId)}?after=${cursor}`,
            {signal}
        );
        if(!response.ok) throw new Error("Could not read CYN-X Core events.");

        const data = await response.json();
        for(const event of data.events || []){
            cursor = Math.max(cursor, event.id);
            if(requestId === activePipelineRequestId){
                handlePipelineEvent(event);
            }
        }
        if(data.done) return true;
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return false;
}

function startLoading(requestId){
    const thinking = document.getElementById("thinking");
    if(thinking) thinking.style.display = "flex";
    activePipelineRequestId = requestId;
    resetPipeline();
    startTime = Date.now();
    clearInterval(timerInterval);
    timerInterval = setInterval(updateTimer, 100);
}

function stopLoading(requestId){
    if(requestId !== activePipelineRequestId) return;
    const thinking = document.getElementById("thinking");
    if(thinking) thinking.style.display = "none";
    if(startTime) lastResponseTime = (Date.now() - startTime) / 1000;
    clearInterval(timerInterval);
    updateResponseTime();
}

async function cancelActiveRequest(){
    const requestId = activePipelineRequestId;
    if(!requestId) return;

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
        }
    }catch(error){
        if(requestId === activePipelineRequestId){
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = error.message;
            const cancelButton = document.getElementById("pipeline-cancel");
            if(cancelButton) cancelButton.disabled = true;
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

                Date.now()

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





    const input =

        document.getElementById(

            "message"

        );





    const text =

        input.value.trim();





    if(!text)

        return;





    addMessage(

        "You: " + text

    );





    input.value = "";





    const requestId = window.crypto && window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const eventController = new AbortController();
    startLoading(requestId);
    const pipelinePromise = watchPipelineEvents(
        requestId,
        eventController.signal
    ).catch((error) => {
        if(!eventController.signal.aborted && requestId === activePipelineRequestId){
            document.querySelectorAll('.pipeline-stage[data-status="active"]').forEach(
                (active) => active.dataset.status = "failed"
            );
            setPipelineStage("completed", "failed");
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = error.message;
        }
        return false;
    });





    try{



        // --------------------------

        // Get active prompt layers

        // --------------------------



        const promptLayers =

            getPromptLayers();





        const responsePromise = fetch(

                "/chat",

                {

                    method:"POST",



                    headers:{

                        "Content-Type":

                        "application/json"

                    },



                    body:

                    JSON.stringify({

                        message: text,

                        prompt_layers:
                            promptLayers,
                        request_id: requestId

                    })



                }

            );

        const fetchedResponse = await responsePromise;





        const data =

            await fetchedResponse.json();

        if(!fetchedResponse.ok){
            throw new Error(
                data.detail || "CYN-X Core could not complete this request."
            );
        }

        await pipelinePromise;

        if(data.cancelled){
            addMessage("[Request cancelled.]");
            stopLoading(requestId);
            return;
        }





        // --------------------------

        // Sync returned layer state

        // --------------------------



        if(

            data.prompt_layers

        ){



            setPromptLayers(

                data.prompt_layers

            );



            detectPromptPreset();



        }





        const cynResponse =

            data.response;



        if (

            cynResponse &&

            typeof cynResponse === "object"

        ) {

            addMessage(

                "Cyn: " +

                (cynResponse.text || "")

            );



            if (cynResponse.chart) {

                addChart(

                    cynResponse.chart

                );

            }

        }

        else {

            addMessage(

                "Cyn: "

                +

                (cynResponse || "")

            );

        }

        stopLoading(requestId);




    }





    catch(error){

        eventController.abort();
        const active = document.querySelector(
            '.pipeline-stage[data-status="active"]'
        );
        if(active && requestId === activePipelineRequestId){
            active.dataset.status = "failed";
            const status = document.getElementById("pipeline-status");
            if(status) status.textContent = error.message;
        }
        stopLoading(requestId);



        addMessage(

            "[ERROR] "

            +

            error.message

        );



    }



}













// ==========================

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

        const text = message.substring(4);

        div.innerHTML =

            '<span class="you-name">You:</span>' +

            '<span class="you-text">' +

            escapeHTML(text) +

            '</span>';

    }

    else if (message.startsWith("Cyn:")) {

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





    const input =

        document.getElementById(

            "message"

        );





    if(input){



        input.addEventListener(

            "keydown",

            function(event){



                if(

                    event.key === "Enter"

                ){

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
