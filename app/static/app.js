document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const extractUrl = body.dataset.extractUrl || "/extract/from-file";
    const maxUploadMb = Number(body.dataset.maxUploadMb || "10");

    let selectedFile = null;

    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const filePill = document.getElementById("filePill");
    const fileName = document.getElementById("fileName");
    const clearFileBtn = document.getElementById("clearFileBtn");

    const submitBtn = document.getElementById("submitBtn");
    const submitSpinner = document.getElementById("submitSpinner");
    const submitLabel = document.getElementById("submitLabel");

    const errorBanner = document.getElementById("errorBanner");
    const errorMessage = document.getElementById("errorMessage");
    const warnBanner = document.getElementById("warnBanner");
    const warnMessage = document.getElementById("warnMessage");

    const resultsSection = document.getElementById("resultsSection");
    const nameField = document.getElementById("nameField");
    const accountField = document.getElementById("accountField");
    const nameValue = document.getElementById("nameValue");
    const accountValue = document.getElementById("accountValue");

    const metaSource = document.getElementById("metaSource");
    const metaInput = document.getElementById("metaInput");
    const metaProcessed = document.getElementById("metaProcessed");
    const metaLlm = document.getElementById("metaLlm");
    const metaFallback = document.getElementById("metaFallback");

    const resetBtn = document.getElementById("resetBtn");

    if (
        !dropZone || !fileInput || !filePill || !fileName || !clearFileBtn ||
        !submitBtn || !submitSpinner || !submitLabel || !errorBanner ||
        !errorMessage || !warnBanner || !warnMessage || !resultsSection ||
        !nameField || !accountField || !nameValue || !accountValue ||
        !metaSource || !metaInput || !metaProcessed || !metaLlm ||
        !metaFallback || !resetBtn
    ) {
        console.error("Some required UI elements were not found.");
        return;
    }

    dropZone.addEventListener("dragover", (event) => {
        event.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (event) => {
        event.preventDefault();
        dropZone.classList.remove("drag-over");

        const droppedFile = event.dataTransfer.files && event.dataTransfer.files[0];
        if (droppedFile) {
            setFile(droppedFile);
        }
    });

    fileInput.addEventListener("change", () => {
        const chosenFile = fileInput.files && fileInput.files[0];
        if (chosenFile) {
            setFile(chosenFile);
        }
    });

    clearFileBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        clearFile();
    });

    submitBtn.addEventListener("click", async () => {
        if (!selectedFile) {
            showError("Please select a .txt file first.");
            return;
        }

        hideBanners();
        setLoading(true);

        const formData = new FormData();
        formData.append("file", selectedFile);

        try {
            const response = await fetch(extractUrl, {
                method: "POST",
                body: formData,
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                showError(result.detail || result.message || `Server error (HTTP ${response.status})`);
                return;
            }

            renderResults(result);
            body.classList.remove("page-locked");
            body.classList.add("page-scrollable");
        } catch (error) {
            console.error(error);
            showError("Could not reach the extraction service. Please check the server is running.");
        } finally {
            setLoading(false);
        }
    });

    resetBtn.addEventListener("click", () => {
        resetUi();
    });

    function setFile(file) {
        hideBanners();

        if (!file.name.toLowerCase().endsWith(".txt")) {
            showError("Only .txt files are supported. Please upload a plain text file.");
            return;
        }

        if (file.size > maxUploadMb * 1024 * 1024) {
            showError(`File is too large. Maximum allowed size is ${maxUploadMb} MB.`);
            return;
        }

        selectedFile = file;
        fileName.textContent = file.name;
        filePill.classList.add("visible");
        submitBtn.disabled = false;
        resultsSection.classList.remove("visible");
    }

    function clearFile() {
        selectedFile = null;
        fileInput.value = "";
        fileName.textContent = "";
        filePill.classList.remove("visible");
        submitBtn.disabled = true;
        hideBanners();
        resultsSection.classList.remove("visible");
    }

    function renderResults(result) {
        const data = result.data || {};
        const meta = result.meta || {};

        if (data.name) {
            nameValue.textContent = data.name;
            nameValue.classList.remove("null-value");
            nameField.classList.add("found");
        } else {
            nameValue.textContent = "Not found";
            nameValue.classList.add("null-value");
            nameField.classList.remove("found");
        }

        if (data.account_number) {
            accountValue.textContent = data.account_number;
            accountValue.classList.remove("null-value");
            accountField.classList.add("found");
        } else {
            accountValue.textContent = "Not found";
            accountValue.classList.add("null-value");
            accountField.classList.remove("found");
        }

        hideBanners();

        if (!data.name || !data.account_number) {
            const missingFields = [
                !data.name ? "customer name" : null,
                !data.account_number ? "account number" : null,
            ].filter(Boolean).join(" and ");

            showWarn(
                `Could not extract ${missingFields}. The document may not contain these fields in a recognised format.`
            );
        }

        metaSource.textContent = meta.source || "—";
        metaInput.textContent = typeof meta.input_characters === "number"
            ? `${meta.input_characters.toLocaleString()} chars`
            : "—";
        metaProcessed.textContent = typeof meta.preprocessed_characters === "number"
            ? `${meta.preprocessed_characters.toLocaleString()} chars`
            : "—";
        metaLlm.innerHTML = createBadge(meta.llm_called, "yes", "no");

        if (meta.llm_fallback_used) {
            metaFallback.innerHTML = '<span class="badge badge-warn">yes — regex filled missing field</span>';
        } else {
            metaFallback.innerHTML = '<span class="badge badge-no">no</span>';
        }

        resultsSection.classList.add("visible");
        setTimeout(() => {
            resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
    }

    function createBadge(value, trueLabel, falseLabel) {
        if (value) {
            return `<span class="badge badge-yes">${trueLabel}</span>`;
        }
        return `<span class="badge badge-no">${falseLabel}</span>`;
    }

    function resetUi() {
        clearFile();

        nameValue.textContent = "—";
        accountValue.textContent = "—";
        nameValue.classList.remove("null-value");
        accountValue.classList.remove("null-value");
        nameField.classList.remove("found");
        accountField.classList.remove("found");

        metaSource.textContent = "—";
        metaInput.textContent = "—";
        metaProcessed.textContent = "—";
        metaLlm.textContent = "—";
        metaFallback.textContent = "—";

        body.classList.remove("page-scrollable");
        body.classList.add("page-locked");
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function setLoading(isLoading) {
        submitBtn.disabled = isLoading || !selectedFile;
        submitSpinner.classList.toggle("visible", isLoading);
        submitLabel.textContent = isLoading ? "Extracting..." : "Extract data";
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorBanner.classList.add("visible");
    }

    function showWarn(message) {
        warnMessage.textContent = message;
        warnBanner.classList.add("visible");
    }

    function hideBanners() {
        errorBanner.classList.remove("visible");
        warnBanner.classList.remove("visible");
    }
});