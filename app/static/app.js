document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const extractUrl = body.dataset.extractUrl || "/extract/from-file";
    const maxUploadMb = Number(body.dataset.maxUploadMb || "10");

    let selectedFile = null;

    const pageContainer = document.getElementById("pageContainer");
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
    const resetBtn = document.getElementById("resetBtn");
    const resultsPanel = document.getElementById("resultsPanel");
    const resName = document.getElementById("resName");
    const resMasterAcc = document.getElementById("resMasterAcc");
    const resSubAcc = document.getElementById("resSubAcc");
    const resAddress = document.getElementById("resAddress");
    const resFiNum = document.getElementById("resFiNum");

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

        const missing = [
            !data.name ? "customer name" : null,
            !data.master_account_number ? "master account number" : null,
            !data.sub_account_number ? "sub account number" : null,
            !data.address ? "address" : null,
            !data.fi_num ? "FI number" : null,
        ].filter(Boolean);

        if (missing.length) {
            showWarn(`Could not extract: ${missing.join(", ")}.`);
        }

        // Trigger layout split
        pageContainer.classList.add("has-results");

        // Swap buttons
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