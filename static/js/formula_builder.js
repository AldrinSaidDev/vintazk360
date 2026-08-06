(function () {
    "use strict";

    const PRESETS = {
        percentage: {
            inputs: [
                ["Total Exits", "total_exits"],
                ["Average Headcount", "average_headcount"],
            ],
            expression: "total_exits / average_headcount * 100",
        },
        average: {
            inputs: [
                ["First Value", "first_value"],
                ["Second Value", "second_value"],
            ],
            expression: "( first_value + second_value ) / 2",
        },
        sum: {
            inputs: [
                ["First Value", "first_value"],
                ["Second Value", "second_value"],
            ],
            expression: "first_value + second_value",
        },
        difference: {
            inputs: [
                ["Starting Value", "starting_value"],
                ["Ending Value", "ending_value"],
            ],
            expression: "ending_value - starting_value",
        },
        ratio: {
            inputs: [
                ["Numerator", "numerator"],
                ["Denominator", "denominator"],
            ],
            expression: "numerator / denominator",
        },
        custom_score: {
            inputs: [
                ["Achieved Value", "achieved_value"],
                ["Target Value", "target_value"],
                ["Weight", "weight"],
            ],
            expression: "( achieved_value / target_value ) * weight",
        },
    };

    const OPERATOR_LABELS = { "+": "+", "-": "−", "*": "×", "/": "÷" };
    const VARIABLE_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

    function titleFromVariable(value) {
        return value
            .replace(/_/g, " ")
            .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
    }

    function variableFromLabel(value) {
        return value
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_+|_+$/g, "")
            .replace(/^(?=\d)/, "_");
    }

    function tokenise(expression, inputs) {
        const tokens = [];
        const pattern = /\s*([A-Za-z_][A-Za-z0-9_]*|(?:\d+\.?\d*|\.\d+)|[+\-*/()])\s*/gy;
        let position = 0;

        while (position < expression.length) {
            pattern.lastIndex = position;
            const match = pattern.exec(expression);
            if (!match || match.index !== position) return null;

            const value = match[1];
            position = pattern.lastIndex;

            if (VARIABLE_PATTERN.test(value)) {
                let input = inputs.find(function (item) { return item.variable === value; });
                if (!input) {
                    input = { label: titleFromVariable(value), variable: value };
                    inputs.push(input);
                }
                tokens.push({ type: "input", value: value, label: input.label });
            } else if (/^(?:\d+\.?\d*|\.\d+)$/.test(value)) {
                tokens.push({ type: "constant", value: value, label: value });
            } else if (value === "(" || value === ")") {
                tokens.push({ type: "parenthesis", value: value, label: value });
            } else {
                tokens.push({ type: "operator", value: value, label: OPERATOR_LABELS[value] });
            }
        }

        return tokens;
    }

    function validate(tokens) {
        if (!tokens.length) return { valid: false, message: "Missing operand" };

        let balance = 0;
        let expectsOperand = true;
        let previous = null;

        for (const token of tokens) {
            if (token.type === "operator") {
                if (expectsOperand) {
                    return {
                        valid: false,
                        message: previous && previous.type === "operator"
                            ? "Consecutive operators"
                            : "Missing operand",
                    };
                }
                expectsOperand = true;
            } else if (token.type === "parenthesis" && token.value === "(") {
                if (!expectsOperand) return { valid: false, message: "Missing operator" };
                balance += 1;
            } else if (token.type === "parenthesis" && token.value === ")") {
                if (expectsOperand) return { valid: false, message: "Missing operand" };
                balance -= 1;
                if (balance < 0) return { valid: false, message: "Unmatched parenthesis" };
                expectsOperand = false;
            } else {
                if (!expectsOperand) return { valid: false, message: "Missing operator" };
                expectsOperand = false;
            }
            previous = token;
        }

        if (balance !== 0) return { valid: false, message: "Unmatched parenthesis" };
        if (expectsOperand) return { valid: false, message: "Missing operand" };
        return { valid: true, message: "Formula Valid" };
    }

    function initialiseBuilder(root) {
        const form = root.closest("form");
        const modeInputs = Array.from(root.querySelectorAll("[data-formula-mode]"));
        const presetPanel = root.querySelector("[data-preset-panel]");
        const presetSelect = root.querySelector("[data-preset-select]");
        const inputEditor = root.querySelector("[data-input-editor]");
        const inputLabel = root.querySelector("[data-input-label]");
        const inputVariable = root.querySelector("[data-input-variable]");
        const inputError = root.querySelector("[data-input-error]");
        const inputList = root.querySelector("[data-input-list]");
        const canvas = root.querySelector("[data-formula-canvas]");
        const expressionField = root.querySelector("[data-expression-field]");
        const expressionPreview = root.querySelector("[data-expression-preview]");
        const humanPreview = root.querySelector("[data-human-preview]");
        const validationStatus = root.querySelector("[data-formula-validation]");
        const submitButton = form ? form.querySelector('button[type="submit"]') : null;

        const state = { inputs: [], tokens: [], draggedIndex: null };
        let variableWasEdited = false;
        let currentValidation = { valid: false, message: "Missing operand" };

        function setEditorVisibility(isVisible) {
            inputEditor.classList.toggle("hidden", !isVisible);
            if (isVisible) {
                inputLabel.focus();
            } else {
                inputLabel.value = "";
                inputVariable.value = "";
                inputError.textContent = "";
                inputError.classList.add("hidden");
                variableWasEdited = false;
            }
        }

        function expressionValue() {
            return state.tokens.map(function (token) { return token.value; }).join(" ");
        }

        function humanValue() {
            return state.tokens.map(function (token) {
                if (token.type === "operator") return OPERATOR_LABELS[token.value];
                return token.label;
            }).join(" ");
        }

        function updateOutput() {
            const expression = expressionValue();
            const human = humanValue();
            currentValidation = validate(state.tokens);

            expressionField.value = expression;
            expressionPreview.textContent = expression || "—";
            humanPreview.textContent = human || "—";
            validationStatus.textContent = (currentValidation.valid ? "✓ " : "⚠ ") + currentValidation.message;
            if (currentValidation.valid) {
                validationStatus.className = "mt-3 flex items-center gap-2 rounded-lg border border-brand/20 bg-brand/5 px-3 py-2 text-xs font-semibold text-brand";
            } else if (currentValidation.message === "Missing operator") {
                validationStatus.className = "mt-3 flex items-center gap-2 rounded-lg border border-status-bad/30 bg-status-bad/5 px-3 py-2 text-xs font-semibold text-status-bad";
            } else {
                validationStatus.className = "mt-3 flex items-center gap-2 rounded-lg border border-status-warn/30 bg-status-warn/10 px-3 py-2 text-xs font-semibold text-amber-700";
            }

            if (submitButton) {
                submitButton.disabled = !currentValidation.valid;
                submitButton.classList.toggle("cursor-not-allowed", !currentValidation.valid);
                submitButton.classList.toggle("opacity-50", !currentValidation.valid);
            }
        }

        function renderInputs() {
            inputList.replaceChildren();

            if (!state.inputs.length) {
                const empty = document.createElement("p");
                empty.className = "text-xs italic text-slate-400";
                empty.textContent = "No inputs added yet.";
                inputList.appendChild(empty);
                return;
            }

            state.inputs.forEach(function (input) {
                const item = document.createElement("div");
                item.className = "group inline-flex items-center overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm";

                const insert = document.createElement("button");
                insert.type = "button";
                insert.className = "inline-flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-brand/5 hover:text-brand";
                insert.setAttribute("aria-label", "Add " + input.label + " to formula");
                insert.innerHTML = '<span class="h-2 w-2 rounded-sm bg-accent" aria-hidden="true"></span>';
                insert.appendChild(document.createTextNode(input.label));
                insert.addEventListener("click", function () {
                    state.tokens.push({ type: "input", value: input.variable, label: input.label });
                    renderCanvas();
                });

                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "border-l border-slate-200 px-2.5 py-2 text-sm text-slate-400 transition hover:bg-status-bad/5 hover:text-status-bad";
                remove.setAttribute("aria-label", "Remove input " + input.label);
                remove.textContent = "×";
                remove.addEventListener("click", function () {
                    state.inputs = state.inputs.filter(function (item) { return item.variable !== input.variable; });
                    state.tokens = state.tokens.filter(function (token) {
                        return token.type !== "input" || token.value !== input.variable;
                    });
                    renderInputs();
                    renderCanvas();
                });

                item.append(insert, remove);
                inputList.appendChild(item);
            });
        }

        function renderCanvas() {
            canvas.replaceChildren();

            if (!state.tokens.length) {
                const empty = document.createElement("li");
                empty.className = "w-full self-center text-center text-xs text-slate-400";
                empty.textContent = "Select an input or operator to begin.";
                canvas.appendChild(empty);
                updateOutput();
                return;
            }

            state.tokens.forEach(function (token, index) {
                const item = document.createElement("li");
                item.draggable = true;
                item.dataset.tokenIndex = String(index);
                item.className = token.type === "input"
                    ? "relative flex cursor-grab items-center gap-2 rounded-lg border border-brand/20 bg-brand/5 px-2.5 py-2 text-xs font-semibold text-brand shadow-sm active:cursor-grabbing"
                    : "relative flex cursor-grab items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-semibold text-slate-700 shadow-sm active:cursor-grabbing";

                const dragHandle = document.createElement("span");
                dragHandle.className = "select-none text-slate-300";
                dragHandle.setAttribute("aria-hidden", "true");
                dragHandle.textContent = "⠿";

                const label = document.createElement("span");
                label.textContent = token.type === "operator" ? OPERATOR_LABELS[token.value] : token.label;

                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "absolute -right-2 -top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-white text-xs leading-none text-slate-400 shadow-sm transition hover:border-status-bad/40 hover:bg-status-bad/5 hover:text-status-bad";
                remove.setAttribute("aria-label", "Remove " + label.textContent);
                remove.textContent = "×";
                remove.addEventListener("click", function () {
                    state.tokens.splice(index, 1);
                    renderCanvas();
                });

                item.addEventListener("dragstart", function (event) {
                    state.draggedIndex = index;
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", String(index));
                    window.setTimeout(function () { item.classList.add("opacity-40"); }, 0);
                });
                item.addEventListener("dragend", function () {
                    state.draggedIndex = null;
                    item.classList.remove("opacity-40");
                    canvas.querySelectorAll("[data-token-index]").forEach(function (element) {
                        element.classList.remove("ring-2", "ring-brand/20");
                    });
                });
                item.addEventListener("dragover", function (event) {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                    item.classList.add("ring-2", "ring-brand/20");
                });
                item.addEventListener("dragleave", function () {
                    item.classList.remove("ring-2", "ring-brand/20");
                });
                item.addEventListener("drop", function (event) {
                    event.preventDefault();
                    const from = state.draggedIndex;
                    if (from === null || from === index) return;
                    const moved = state.tokens.splice(from, 1)[0];
                    state.tokens.splice(index, 0, moved);
                    state.draggedIndex = null;
                    renderCanvas();
                });

                item.append(dragHandle, label, remove);
                canvas.appendChild(item);
            });

            updateOutput();
        }

        function applyPreset(name) {
            const preset = PRESETS[name];
            if (!preset) return;
            state.inputs = preset.inputs.map(function (input) {
                return { label: input[0], variable: input[1] };
            });
            state.tokens = tokenise(preset.expression, state.inputs) || [];
            renderInputs();
            renderCanvas();
        }

        function saveInput() {
            const label = inputLabel.value.trim();
            const variable = inputVariable.value.trim();
            let message = "";

            if (!label || !variable) {
                message = "Enter both a display label and variable name.";
            } else if (!VARIABLE_PATTERN.test(variable)) {
                message = "Use letters, numbers, and underscores; start with a letter or underscore.";
            } else if (state.inputs.some(function (input) { return input.variable === variable; })) {
                message = "That variable name already exists.";
            }

            if (message) {
                inputError.textContent = message;
                inputError.classList.remove("hidden");
                return;
            }

            state.inputs.push({ label: label, variable: variable });
            renderInputs();
            setEditorVisibility(false);
        }

        modeInputs.forEach(function (input) {
            input.addEventListener("change", function () {
                presetPanel.classList.toggle("hidden", input.value !== "preset");
                if (input.value === "preset") applyPreset(presetSelect.value);
            });
        });

        presetSelect.addEventListener("change", function () { applyPreset(presetSelect.value); });
        root.querySelector("[data-add-input]").addEventListener("click", function () { setEditorVisibility(true); });
        root.querySelector("[data-cancel-input]").addEventListener("click", function () { setEditorVisibility(false); });
        root.querySelector("[data-save-input]").addEventListener("click", saveInput);

        inputLabel.addEventListener("input", function () {
            if (!variableWasEdited) inputVariable.value = variableFromLabel(inputLabel.value);
        });
        inputVariable.addEventListener("input", function () { variableWasEdited = true; });
        inputEditor.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                saveInput();
            } else if (event.key === "Escape") {
                setEditorVisibility(false);
            }
        });

        root.querySelector("[data-token-toolbar]").addEventListener("click", function (event) {
            const button = event.target.closest("[data-token-type]");
            if (!button) return;
            const value = button.dataset.tokenValue;
            state.tokens.push({
                type: button.dataset.tokenType,
                value: value,
                label: button.dataset.tokenType === "operator" ? OPERATOR_LABELS[value] : value,
            });
            renderCanvas();
        });

        canvas.addEventListener("dragover", function (event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
        });
        canvas.addEventListener("drop", function (event) {
            if (event.target.closest("[data-token-index]")) return;
            event.preventDefault();
            if (state.draggedIndex === null) return;
            const moved = state.tokens.splice(state.draggedIndex, 1)[0];
            state.tokens.push(moved);
            state.draggedIndex = null;
            renderCanvas();
        });

        if (form) {
            form.addEventListener("submit", function (event) {
                if (!currentValidation.valid) {
                    event.preventDefault();
                    validationStatus.focus();
                }
            });
        }

        const initialExpression = expressionField.value.trim();
        if (initialExpression) {
            state.inputs = [];
            state.tokens = tokenise(initialExpression, state.inputs) || [];
            modeInputs.forEach(function (input) { input.checked = input.value === "custom"; });
            presetPanel.classList.add("hidden");
            renderInputs();
            renderCanvas();
        } else {
            applyPreset(presetSelect.value);
        }
    }

    function initialiseAll() {
        document.querySelectorAll("[data-formula-builder]").forEach(initialiseBuilder);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiseAll);
    } else {
        initialiseAll();
    }
}());
