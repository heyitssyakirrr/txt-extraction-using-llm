"use strict";

document.addEventListener("DOMContentLoaded", function () {

    // --- Config from data attributes on <body> ---
    var body        = document.body;
    var extractUrl  = body.dataset.extractUrl  || "/extract/from-file";
    var maxUploadMb = Number(body.dataset.maxUploadMb || "10");

    var selectedFile = null;

    // --- Element references (IDs match index.html exactly) ---
    var pageContainer  = document.getElementById("pageContainer");
    var dropZone       = document.getElementById("dropZone");
    var fileInput      = document.getElementById("fileInput");
    var filePill       = document.getElementById("filePill");
    var fileName       = document.getElementById("fileName");
    var clearFileBtn   = document.getElementById("clearFileBtn");
    var submitBtn      = document.getElementById("submitBtn");
    var submitSpinner  = document.getElementById("submitSpinner");
    var submitLabel    = document.getElementById("submitLabel");
    var errorBanner    = document.getElementById("errorBanner");
    var errorMessage   = document.getElementById("errorMessage");
    var warnBanner     = document.getElementById("warnBanner");
    var warnMessage    = document.getElementById("warnMessage");
    var resetBtn       = document.getElementById("resetBtn");
    var resName        = document.getElementById("resName");
    var resMasterAcc   = document.getElementById("resMasterAcc");
    var resSubAcc      = document.getElementById("resSubAcc");
    var resAddress     = document.getElementById("resAddress");
    var resFiNum       = document.getElementById("resFiNum");

    // --- Drag-and-drop ---
    dropZone.addEventListener("dragover", function (e) {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", function () {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", function (e) {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        var files = e.dataTransfer && e.dataTransfer.files;
        if (files && files[0]) setFile(files[0]);
    });

    fileInput.addEventListener("change", function () {
        var files = fileInput.files;
        if (files && files[0]) setFile(files[0]);
    });

    clearFileBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        clearFile();
    });

    // --- Submit ---
    submitBtn.addEventListener("click", function () {
        if (!selectedFile) {
            showError("Please select a .txt file first.");
            return;
        }

        hideBanners();
        setLoading(true);

        var formData = new FormData();
        formData.append("file", selectedFile);

        fetch(extractUrl, {
            method: "POST",
            body: formData,
        })
        .then(function (response) {
            return response.json().then(function (result) {
                if (!response.ok || !result.success) {
                    var msg = result.detail || result.message || ("Server error (HTTP " + response.status + ")");
                    showError(msg);
                } else {
                    renderResults(result);
                }
            });
        })
        .catch(function (err) {
            console.error("Fetch error:", err);
            showError("Could not reach the extraction service. Please check the server is running.");
        })
        .finally(function () {
            setLoading(false);
        });
    });

    resetBtn.addEventListener("click", resetUi);

    // --- File helpers ---
    function setFile(file) {
        hideBanners();

        if (!file.name.toLowerCase().endsWith(".txt")) {
            showError("Only .txt files are supported.");
            return;
        }

        if (file.size > maxUploadMb * 1024 * 1024) {
            showError("File too large. Maximum allowed size is " + maxUploadMb + " MB.");
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
        var data = result.data || {};

        setField(resName,      data.name,                   true);
        setField(resMasterAcc, data.master_account_number,  false);
        setField(resSubAcc,    data.sub_account_number,     false);
        setField(resAddress,   data.address,                false);
        setField(resFiNum,     data.fi_num,                 false);

        var missing = [];
        if (!data.name)                  missing.push("customer name");
        if (!data.master_account_number) missing.push("master account no.");
        if (!data.sub_account_number)    missing.push("sub account no.");
        if (!data.address)               missing.push("address");
        if (!data.fi_num)                missing.push("FI number");

        if (missing.length) {
            showWarn("Could not extract: " + missing.join(", ") + ".");
        }

        pageContainer.classList.add("has-results");
        submitBtn.style.display = "none";
        resetBtn.style.display  = "flex";
    }

    function setField(elem, value, isName) {
        if (value) {
            elem.textContent = value;
            elem.className = "field-value found" + (isName ? " is-name" : "");
        } else {
            elem.textContent = "Not found";
            elem.className = "field-value not-found";
        }
    }

    // --- Reset ---
    function resetUi() {
        clearFile();
        hideBanners();

        var fields = [resName, resMasterAcc, resSubAcc, resAddress, resFiNum];
        for (var i = 0; i < fields.length; i++) {
            fields[i].textContent = "\u2014";
            fields[i].className   = "field-value";
        }

        pageContainer.classList.remove("has-results");
        submitBtn.style.display = "";
        resetBtn.style.display  = "none";
    }

    // --- Loading state ---
    function setLoading(isLoading) {
        submitBtn.disabled = isLoading || !selectedFile;
        if (isLoading) {
            submitSpinner.classList.add("visible");
        } else {
            submitSpinner.classList.remove("visible");
        }
        submitLabel.textContent = isLoading ? "Extracting..." : "Extract Data";
    }

    // --- Banners ---
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