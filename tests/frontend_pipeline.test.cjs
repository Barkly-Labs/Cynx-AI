const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
    constructor(id = "") {
        this.id = id;
        this.dataset = {};
        this.style = {};
        this.attributes = new Map();
        this.children = [];
        this.listeners = {};
        this.textContent = "";
        this.innerText = "";
        this.hidden = false;
        this.disabled = false;
        this.open = false;
        this.value = "";
    }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    removeAttribute(name) { this.attributes.delete(name); }
    hasAttribute(name) { return this.attributes.has(name); }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren(...children) { this.children = children; }
    addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
    focus() { this.ownerDocument.activeElement = this; }
    getClientRects() { return this.hidden ? [] : [{}]; }
    contains(element) { return element === this || this.children.some((child) => child.contains?.(element)); }
    querySelector(selector) {
        if(selector.startsWith(".stage-label")) return this.parts?.label || null;
        if(selector.startsWith(".stage-state")) return this.parts?.state || null;
        if(selector.startsWith(".stage-detail")) return this.parts?.detail || null;
        if(selector.startsWith(".stage-time")) return this.parts?.time || null;
        if(selector.startsWith(".pipeline-stage[data-stage=")) {
            return this.ownerDocument.findStage(selector)?.querySelector(selector.split(" ").pop()) || null;
        }
        return null;
    }
    querySelectorAll(selector) {
        if(selector === "button:not(:disabled):not([hidden]), summary, [tabindex]:not([tabindex=\"-1\"])" || selector.startsWith("button:not(:disabled)")) {
            return this.ownerDocument.focusable.filter((item) => !item.hidden && !item.disabled);
        }
        return [];
    }
}

function makePipelineDom(){
    const ids = [
        "thinking", "pipeline-tools", "pipeline-status", "pipeline-view-state",
        "pipeline-cancel", "pipeline-keep-open", "pipeline-resume", "pipeline-dismiss",
        "pipeline-outcome", "pipeline-outcome-title", "pipeline-outcome-message",
        "pipeline-failure-details", "pipeline-failure-list", "pipeline-retention-message",
        "timer", "response-time"
    ];
    const elements = new Map(ids.map((id) => [id, new FakeElement(id)]));
    const stages = [
        ["request_received", "Request received"],
        ["understanding", "Understanding request and context"],
        ["evaluating_capabilities", "Evaluating available capabilities"],
        ["decision", "Decision"],
        ["tool_execution", "Tool execution"],
        ["generating_response", "Generating response"],
        ["completed", "Completed"]
    ].map(([name, label], i) => {
        const item = new FakeElement(`stage-${name}`);
        item.dataset.stage = name;
        item.dataset.status = "pending";
        item.parts = {
            label: new FakeElement(),
            state: new FakeElement(),
            detail: new FakeElement(),
            time: new FakeElement()
        };
        item.parts.label.textContent = label;
        item.parts.state.textContent = "Pending";
        item.parts.indicator = new FakeElement();
        item.parts.indicator.dataset.step = String(i + 1).padStart(2, "0");
        item.ownerDocument = null;
        item.removeAttribute = function(name){ this.attributes.delete(name); };
        item.setAttribute = function(name, value){ this.attributes.set(name, String(value)); };
        return item;
    });
    const originalQuerySelector = FakeElement.prototype.querySelector;
    const document = {
        activeElement: new FakeElement("message"),
        focusable: [],
        addEventListener() {},
        getElementById(id) { return elements.get(id) || null; },
        createElement() {
            const item = new FakeElement();
            item.ownerDocument = document;
            return item;
        },
        findStage(selector){
            const match = selector.match(/data-stage=["']([^"']+)["']/);
            return match ? stages.find((item) => item.dataset.stage === match[1]) || null : null;
        },
        querySelector(selector){
            if(selector.startsWith(".pipeline-stage[data-stage=")){
                const stage = document.findStage(selector);
                if(!stage) return null;
                if(selector.includes(".stage-label")) return stage.parts.label;
                if(selector.includes(".stage-detail")) return stage.parts.detail;
                return stage;
            }
            return null;
        },
        querySelectorAll(selector){
            if(selector === ".pipeline-stage") return stages;
            if(selector === ".pipeline-stage[aria-current]") return stages.filter((item) => item.hasAttribute("aria-current"));
            if(selector === '.pipeline-stage[data-status="active"]') return stages.filter((item) => item.dataset.status === "active");
            return [];
        }
    };
    elements.forEach((element) => { element.ownerDocument = document; });
    document.activeElement.ownerDocument = document;
    stages.forEach((item) => { item.ownerDocument = document; });
    const panel = elements.get("thinking");
    panel.contains = (element) => element === panel || elements.get("pipeline-dismiss") === element
        || elements.get("pipeline-cancel") === element;
    panel.querySelectorAll = (selector) => selector.startsWith("button:not(:disabled)") ? document.focusable : [];
    elements.get("pipeline-tools").replaceChildren = function(...children){this.children=children;};
    elements.get("pipeline-failure-list").replaceChildren = function(...children){this.children=children;};
    return {document, elements, stages};
}

function createHarness(){
    const {document, elements, stages} = makePipelineDom();
    let nextTimer = 1;
    const timers = new Map();
    const intervals = new Map();
    let now = 0;
    const context = {
        document,
        window: {crypto: {randomUUID: () => "generated-id"}},
        console,
        performance: {now: () => now},
        setTimeout(callback, delay){const id=nextTimer++;timers.set(id,{callback,delay});return id;},
        clearTimeout(id){timers.delete(id);},
        setInterval(callback, delay){const id=nextTimer++;intervals.set(id,{callback,delay});return id;},
        clearInterval(id){intervals.delete(id);},
        AbortController,
        fetch: async () => { throw new Error("fetch unused by lifecycle harness"); }
    };
    vm.createContext(context);
    const scriptPath = path.join(__dirname, "../interfaces/web/static/chat.js");
    vm.runInContext(fs.readFileSync(scriptPath, "utf8"), context, {filename: scriptPath});
    return {
        context, document, elements, stages, timers, intervals,
        start(id){context.startLoading(id);},
        event(id, type, payload={}){context.handlePipelineEvent({type, ...payload}, id);},
        read(expression){return vm.runInContext(expression, context);},
        runTimeout(id){const timer=timers.get(id);assert.ok(timer);timers.delete(id);timer.callback();return timer.delay;},
        advance(ms){now+=ms;}
    };
}

function completeSuccessfully(h, requestId="success"){
    h.start(requestId);
    h.event(requestId,"stage",{stage:"request_received",status:"completed"});
    h.event(requestId,"stage",{stage:"understanding",status:"active"});
    h.event(requestId,"stage",{stage:"understanding",status:"completed"});
    h.event(requestId,"stage",{stage:"evaluating_capabilities",status:"completed"});
    h.event(requestId,"decision",{action:"answer_directly",tools:[]});
    h.event(requestId,"stage",{stage:"generating_response",status:"completed"});
    h.event(requestId,"request_completed");
}

test("success stays visible with all completed stages for 15 seconds", () => {
    const h=createHarness();
    completeSuccessfully(h);
    assert.equal(h.elements.get("thinking").style.display,"flex");
    assert.equal(h.elements.get("pipeline-outcome").dataset.kind,"success");
    assert.equal(h.elements.get("pipeline-outcome-title").textContent,"Completed successfully");
    assert.ok(h.stages.every((stage)=>stage.dataset.status==="completed"));
    assert.equal(h.read("pipelineRemainingMs"),15000);
    const timerId=h.read("pipelineDismissTimeout");
    assert.equal(h.runTimeout(timerId),15000);
    assert.equal(h.elements.get("thinking").style.display,"none");
});

test("tool failures are listed individually and completed requests are marked partial", () => {
    const h=createHarness();
    h.start("partial");
    h.event("partial","decision",{action:"use_tools",tools:["web_search","calculator","filesystem"]});
    h.event("partial","tool",{status:"started",name:"web_search",invocation_id:"a"});
    h.event("partial","tool",{status:"failed",name:"web_search",invocation_id:"a",message:"SECRET stack and token"});
    h.event("partial","tool",{status:"started",name:"calculator",invocation_id:"b"});
    h.event("partial","tool",{status:"failed",name:"calculator",invocation_id:"b"});
    h.event("partial","tool",{status:"started",name:"filesystem",invocation_id:"c"});
    h.event("partial","tool",{status:"completed",name:"filesystem",invocation_id:"c"});
    h.event("partial","stage",{stage:"generating_response",status:"completed"});
    h.event("partial","request_completed");
    assert.equal(h.elements.get("pipeline-outcome").dataset.kind,"partial");
    const diagnostics=h.elements.get("pipeline-failure-list").children.map((item)=>item.textContent).join("\n");
    assert.match(diagnostics,/web_search/);
    assert.match(diagnostics,/calculator/);
    assert.doesNotMatch(diagnostics,/SECRET|stack|token/);
    assert.match(diagnostics,/Retry availability was not reported/);
    assert.equal(h.read("pipelineRemainingMs"),30000);
    assert.equal(h.stages.find((stage)=>stage.dataset.stage==="tool_execution").dataset.status,"failed");
});

test("request failure marks the active stage and retains diagnostics for 30 seconds", () => {
    const h=createHarness();
    h.start("failed");
    h.event("failed","stage",{stage:"generating_response",status:"active"});
    h.event("failed","request_failed",{message:"raw exception should not be shown"});
    assert.equal(h.stages.find((s)=>s.dataset.stage==="generating_response").dataset.status,"failed");
    assert.equal(h.stages.find((s)=>s.dataset.stage==="completed").parts.label.textContent,"Request failed");
    assert.equal(h.elements.get("pipeline-outcome").dataset.kind,"failure");
    const diagnostics=h.elements.get("pipeline-failure-list").children.map((item)=>item.textContent).join("\n");
    assert.match(diagnostics,/Generating response/);
    assert.doesNotMatch(diagnostics,/raw exception/);
    assert.equal(h.read("pipelineRemainingMs"),30000);
});

test("known retryability is shown without triggering an automatic retry", () => {
    const h=createHarness();
    h.start("retry");
    h.event("retry","tool",{status:"failed",name:"web_search",invocation_id:"retry-call",retryable:true});
    h.event("retry","request_failed");
    const diagnostics=h.elements.get("pipeline-failure-list").children.map((item)=>item.textContent).join("\n");
    assert.match(diagnostics,/Retry may be possible/);
    assert.equal(h.read("pipelineTools.size"),1);
    assert.equal(h.read("pipelineRequestRunning"),false);
});

test("cancellation is retained as cancellation, not failure", () => {
    const h=createHarness();
    h.start("cancelled");
    h.event("cancelled","stage",{stage:"tool_execution",status:"active"});
    h.event("cancelled","request_cancelled",{message:"not rendered"});
    assert.equal(h.elements.get("pipeline-outcome").dataset.kind,"cancelled");
    assert.equal(h.stages.find((s)=>s.dataset.stage==="tool_execution").dataset.status,"cancelled");
    assert.equal(h.stages.find((s)=>s.dataset.stage==="completed").parts.label.textContent,"Request cancelled");
    assert.equal(h.elements.get("pipeline-failure-list").children.length,0);
});

test("late completion from an older request cannot overwrite a newer request", () => {
    const h=createHarness();
    completeSuccessfully(h,"old");
    const oldView=h.elements.get("pipeline-view-state").textContent;
    h.start("new");
    h.event("old","request_failed");
    assert.equal(h.read("activePipelineRequestId"),"new");
    assert.equal(h.read("pipelineRequestRunning"),true);
    assert.equal(h.elements.get("pipeline-view-state").textContent,"LIVE REQUEST TRACE");
    assert.notEqual(h.elements.get("pipeline-view-state").textContent,oldView);
    assert.equal(h.stages.every((stage)=>stage.dataset.status==="pending"),true);
});

test("manual dismissal hides a finished pipeline and restores focus", () => {
    const h=createHarness();
    h.context.initializePromptLayers=()=>{};
    h.context.window.onload();
    const returnFocus=h.document.activeElement;
    completeSuccessfully(h);
    h.elements.get("pipeline-dismiss").listeners.click[0]();
    assert.equal(h.elements.get("thinking").style.display,"none");
    assert.equal(h.document.activeElement,returnFocus);
});

test("reading the panel pauses auto-dismiss until resumed", () => {
    const h=createHarness();
    h.context.initializePromptLayers=()=>{};
    h.context.window.onload();
    completeSuccessfully(h);
    const timerId=h.read("pipelineDismissTimeout");
    h.elements.get("thinking").listeners.pointerdown[0]();
    assert.equal(h.read("pipelineDismissPaused"),true);
    assert.equal(h.read("pipelineDismissTimeout"),null);
    assert.equal(h.elements.get("thinking").style.display,"flex");
    h.context.resumePipelineAutoDismiss();
    assert.equal(h.read("pipelineDismissPaused"),false);
    const resumedId=h.read("pipelineDismissTimeout");
    assert.notEqual(resumedId,timerId);
    h.runTimeout(resumedId);
    assert.equal(h.elements.get("thinking").style.display,"none");
});

test("keep-open pin prevents the timer from closing the panel", () => {
    const h=createHarness();
    h.context.initializePromptLayers=()=>{};
    h.context.window.onload();
    completeSuccessfully(h);
    const timerId=h.read("pipelineDismissTimeout");
    h.elements.get("thinking").listeners.pointerdown[0]();
    h.elements.get("pipeline-keep-open").listeners.click[0]();
    assert.equal(h.read("pipelinePinned"),true);
    assert.equal(h.read("pipelineDismissTimeout"),null);
    assert.equal(h.elements.get("thinking").style.display,"flex");
    assert.equal(h.timers.has(timerId),false);
});

test("a running request never receives an automatic dismissal timer", () => {
    const h=createHarness();
    h.start("running");
    assert.equal(h.read("pipelineRequestRunning"),true);
    assert.equal(h.read("pipelineDismissTimeout"),null);
    assert.equal(h.elements.get("thinking").style.display,"flex");
    assert.equal(h.elements.get("pipeline-dismiss").hidden,true);
});

test("markup keeps accessible diagnostics controls and the seven existing stages", () => {
    const html=fs.readFileSync(path.join(__dirname,"../interfaces/web/templates/chat.html"),"utf8");
    assert.equal((html.match(/class="pipeline-stage"/g)||[]).length,7);
    assert.match(html,/id="pipeline-dismiss"[^>]*aria-label=/);
    assert.match(html,/id="pipeline-keep-open"[^>]*aria-pressed=/);
    assert.match(html,/id="pipeline-failure-details"[^>]*hidden/);
    assert.match(html,/role="region"/);
    assert.doesNotMatch(html,/aria-modal=/);
});
