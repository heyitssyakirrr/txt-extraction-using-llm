document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const extractUrl = body.dataset.extractUrl || "/extract/from-file";
    const maxUploadMb = Number(body.dataset.maxUploadMb || "10");

    let selectedFile = null;

    // --- Get elements ---
    const elements = {
        pageContainer: document.getElementById("pageContainer"),
        dropZone: document.getElementById("dropZone"),
        fileInput: document.getElementById("fileInput"),
        filePill: document.getElementById("filePill"),
        fileName: document.getElementById("fileName"),
        clearFileBtn: document.getElementById("clearFileBtn"),
        submitBtn: document.getElementById("submitBtn"),
        submitSpinner: document.getElementById("submitSpinner"),
        submitLabel: document.getElementById("submitLabel"),
        errorBanner: document.getElementById("errorBanner"),
        errorMessage: document.getElementById("errorMessage"),
        warnBanner: document.getElementById("warnBanner"),
        warnMessage: document.getElementById("warnMessage"),
        resetBtn: document.getElementById("resetBtn"),
        resultsPanel: document.getElementById("resultsPanel"),
        resName: document.getElementById("resName"),
        resMasterAcc: document.getElementById("resMasterAcc"),
        resSubAcc: document.getElementById("resSubAcc"),
        resAddress: document.getElementById("resAddress"),
        resFiNum: document.getElementById("resFiNum"),
    };

    // --- Validate elements ---
    const missing = Object.entries(elements)
        .filter(([_, el]) => !el)
        .map(([key]) => key);

    if (missing.length > 0) {
        console.error("❌ Missing UI elements:", missing);
        return;
    }

    // Destructure after validation
    const {
        pageContainer,
        dropZone,
        fileInput,
        filePill,
        fileName,
        clearFileBtn,
        submitBtn,
        submitSpinner,
        submitLabel,
        errorBanner,
        errorMessage,
        warnBanner,
        warnMessage,
        resetBtn,
        resName,
        resMasterAcc,
        resSubAcc,
        resAddress,
        resFiNum
    } = elements;

    // --- Drag and drop ---
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) setFile(f);
    });

    fileInput.addEventListener("change", () => {
        const f = fileInput.files && fileInput.files[0];
        if (f) setFile(f);
    });

    clearFileBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        clearFile();
    });

    // --- Submit ---
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
        } catch (err) {
            console.error(err);
            showError("Could not reach the extraction service. Please check the server is running.");
        } finally {
            setLoading(false);
        }
    });

    resetBtn.addEventListener("click", () => resetUi());

    // --- File helpers ---
    function setFile(file) {
        hideBanners();

        if (!file.name.toLowerCase().endsWith(".txt")) {
            showError("Only .txt files are supported.");
            return;
        }

        if (file.size > maxUploadMb * 1024 * 1024) {
            showError(`File too large. Maximum allowed size is ${maxUploadMb} MB.`);
            return;
        }

        selectedFile = file;
        fileName.textContent = file.name;
        filePill.classList.add("visible");
        submitBtn.disabled = false;
    }

    function clearFile() {
        selectedFile = null;
        fileInput.value = "";
        fileName.textContent = "";
        filePill.classList.remove("visible");
        submitBtn.disabled = true;
        hideBanners();
    }

    // --- Render results ---
    function renderResults(result) {
        const data = result.data || {};

        setField(resName, data.name);
        setField(resMasterAcc, data.master_account_number);
        setField(resSubAcc, data.sub_account_number);
        setField(resAddress, data.address);
        setField(resFiNum, data.fi_num);

        const missingFields = [
            !data.name ? "customer name" : null,
            !data.master_account_number ? "master account number" : null,
            !data.sub_account_number ? "sub account number" : null,
            !data.address ? "address" : null,
            !data.fi_num ? "FI number" : null,
        ].filter(Boolean);

        if (missingFields.length) {
            showWarn(`Could not extract: ${missingFields.join(", ")}.`);
        }

        pageContainer.classList.add("has-results");
        submitBtn.style.display = "none";
        resetBtn.style.display = "flex";
    }

    function setField(el, value) {
        if (value) {
            el.textContent = value;
            el.classList.add("found");
            el.classList.remove("not-found");
        } else {
            el.textContent = "Not found";
            el.classList.add("not-found");
            el.classList.remove("found");
        }
    }

    // --- Reset ---
    function resetUi() {
        clearFile();
        hideBanners();

        [resName, resMasterAcc, resSubAcc, resAddress, resFiNum].forEach(el => {
            el.textContent = "—";
            el.classList.remove("found", "not-found");
        });

        pageContainer.classList.remove("has-results");
        submitBtn.style.display = "flex";
        resetBtn.style.display = "none";
    }

    // --- UI state ---
    function setLoading(isLoading) {
        submitBtn.disabled = isLoading || !selectedFile;
        submitSpinner.classList.toggle("visible", isLoading);
        submitLabel.textContent = isLoading ? "Extracting..." : "Extract Data";
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorBanner.classList.add("visible");
    }

    function showWarn(msg) {
        warnMessage.textContent = msg;
        warnBanner.classList.add("visible");
    }

    function hideBanners() {
        errorBanner.classList.remove("visible");
        warnBanner.classList.remove("visible");
    }
});