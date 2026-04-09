document.addEventListener("DOMContentLoaded", function () {

    var maxUploadMb = Number(document.body.dataset.maxUploadMb || "10");

    // -------------------------------------------------------------------------
    // TAB SWITCHING
    // -------------------------------------------------------------------------
    window.switchTab = function (tab) {
        document.getElementById("panelExtract").style.display   = tab === "extract"   ? "" : "none";
        document.getElementById("panelSummarise").style.display = tab === "summarise" ? "" : "none";
        document.getElementById("tabExtract").classList.toggle("active",   tab === "extract");
        document.getElementById("tabSummarise").classList.toggle("active", tab === "summarise");
    };

    // -------------------------------------------------------------------------
    // GENERIC UPLOAD WIDGET FACTORY
    // -------------------------------------------------------------------------
    function createUploadWidget(cfg) {
        var selectedFile = null;

        var dropZone      = document.getElementById(cfg.dropZoneId);
        var fileInput     = document.getElementById(cfg.fileInputId);
        var filePill      = document.getElementById(cfg.filePillId);
        var fileName      = document.getElementById(cfg.fileNameId);
        var clearFileBtn  = document.getElementById(cfg.clearFileBtnId);
        var submitBtn     = document.getElementById(cfg.submitBtnId);
        var submitSpinner = document.getElementById(cfg.submitSpinnerId);
        var submitLabel   = document.getElementById(cfg.submitLabelId);
        var errorBanner   = document.getElementById(cfg.errorBannerId);
        var errorMessage  = document.getElementById(cfg.errorMessageId);
        var warnBanner    = document.getElementById(cfg.warnBannerId);
        var warnMessage   = document.getElementById(cfg.warnMessageId);
        var resetBtn      = document.getElementById(cfg.resetBtnId);
        var pageContainer = document.getElementById(cfg.pageContainerId);

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
            var f = e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) setFile(f);
        });
        fileInput.addEventListener("change", function () {
            var f = fileInput.files && fileInput.files[0];
            if (f) setFile(f);
        });
        clearFileBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            clearFile();
        });

        submitBtn.addEventListener("click", function () {
            if (!selectedFile) {
                showError("Please select a file first.");
                return;
            }
            hideBanners();
            setLoading(true);

            var formData = new FormData();
            formData.append("file", selectedFile);

            fetch(cfg.extractUrl, { method: "POST", body: formData })
                .then(function (response) {
                    return response.json().then(function (result) {
                        return { ok: response.ok, status: response.status, result: result };
                    });
                })
                .then(function (obj) {
                    if (!obj.ok || !obj.result.success) {
                        showError(obj.result.detail || obj.result.message || ("Server error (HTTP " + obj.status + ")"));
                        return;
                    }
                    cfg.onResults(obj.result);
                    pageContainer.classList.add("has-results");
                    submitBtn.style.display = "none";
                    resetBtn.style.display  = "flex";
                })
                .catch(function (err) {
                    console.error(err);
                    showError("Could not reach the service. Please check the server is running.");
                })
                .finally(function () {
                    setLoading(false);
                });
        });

        resetBtn.addEventListener("click", function () {
            clearFile();
            hideBanners();
            cfg.onReset();
            pageContainer.classList.remove("has-results");
            submitBtn.style.display = "";
            resetBtn.style.display  = "none";
        });

        function setFile(file) {
            hideBanners();
            var lower = file.name.toLowerCase();
            if (!lower.endsWith(".txt") && !lower.endsWith(".pdf") && !lower.endsWith(".md")) {
                showError("Only .txt, .pdf, and .md files are supported.");
                return;
            }
            if (file.size > maxUploadMb * 1024 * 1024) {
                showError("File too large. Maximum allowed size is " + maxUploadMb + " MB.");
                return;
            }
            selectedFile         = file;
            fileName.textContent = file.name;
            filePill.classList.add("visible");
            submitBtn.disabled   = false;
        }

        function clearFile() {
            selectedFile         = null;
            fileInput.value      = "";
            fileName.textContent = "";
            filePill.classList.remove("visible");
            submitBtn.disabled   = true;
            hideBanners();
        }

        function setLoading(isLoading) {
            submitBtn.disabled      = isLoading || !selectedFile;
            submitSpinner.classList.toggle("visible", isLoading);
            submitLabel.textContent = isLoading ? "Processing..." : cfg.submitLabel;
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

        return { showWarn: showWarn };
    }

    // -------------------------------------------------------------------------
    // SHARED FIELD HELPER
    // -------------------------------------------------------------------------
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

    // -------------------------------------------------------------------------
    // CUSTOMER DETAIL EXTRACTION WIDGET
    // -------------------------------------------------------------------------
    var resName      = document.getElementById("resName");
    var resMasterAcc = document.getElementById("resMasterAcc");
    var resSubAcc    = document.getElementById("resSubAcc");
    var resAddress   = document.getElementById("resAddress");
    var resFiNum     = document.getElementById("resFiNum");

    var extractWidget = createUploadWidget({
        dropZoneId:      "dropZoneExtract",
        fileInputId:     "fileInputExtract",
        filePillId:      "filePillExtract",
        fileNameId:      "fileNameExtract",
        clearFileBtnId:  "clearFileBtnExtract",
        submitBtnId:     "submitBtnExtract",
        submitSpinnerId: "submitSpinnerExtract",
        submitLabelId:   "submitLabelExtract",
        errorBannerId:   "errorBannerExtract",
        errorMessageId:  "errorMessageExtract",
        warnBannerId:    "warnBannerExtract",
        warnMessageId:   "warnMessageExtract",
        resetBtnId:      "resetBtnExtract",
        pageContainerId: "pageContainerExtract",
        extractUrl:      "/extract/from-file",
        submitLabel:     "Extract Data",

        onResults: function (result) {
            var data = result.data || {};
            setField(resName,      data.name);
            setField(resMasterAcc, data.master_account_number);
            setField(resSubAcc,    data.sub_account_number);
            setField(resAddress,   data.address);
            setField(resFiNum,     data.fi_num);

            var missing = [];
            if (!data.name)                  missing.push("customer name");
            if (!data.master_account_number) missing.push("master account number");
            if (!data.sub_account_number)    missing.push("sub account number");
            if (!data.address)               missing.push("address");
            if (!data.fi_num)                missing.push("FI number");
            if (missing.length) extractWidget.showWarn("Could not extract: " + missing.join(", ") + ".");
        },

        onReset: function () {
            var fields = [resName, resMasterAcc, resSubAcc, resAddress, resFiNum];
            for (var i = 0; i < fields.length; i++) {
                fields[i].textContent = "\u2014";
                fields[i].className   = "field-value";
            }
        }
    });

    // -------------------------------------------------------------------------
    // STATEMENT SUMMARY WIDGET
    // -------------------------------------------------------------------------
    var resOverallMin     = document.getElementById("resOverallMin");
    var resOverallMax     = document.getElementById("resOverallMax");
    var resOverallClosing = document.getElementById("resOverallClosing");
    var resMonthlyTable   = document.getElementById("resMonthlyTable");
    var resDailyTable     = document.getElementById("resDailyTable");

    var summariseWidget = createUploadWidget({
        dropZoneId:      "dropZoneSummarise",
        fileInputId:     "fileInputSummarise",
        filePillId:      "filePillSummarise",
        fileNameId:      "fileNameSummarise",
        clearFileBtnId:  "clearFileBtnSummarise",
        submitBtnId:     "submitBtnSummarise",
        submitSpinnerId: "submitSpinnerSummarise",
        submitLabelId:   "submitLabelSummarise",
        errorBannerId:   "errorBannerSummarise",
        errorMessageId:  "errorMessageSummarise",
        warnBannerId:    "warnBannerSummarise",
        warnMessageId:   "warnMessageSummarise",
        resetBtnId:      "resetBtnSummarise",
        pageContainerId: "pageContainerSummarise",
        extractUrl:      "/summarise/from-file",
        submitLabel:     "Extract Summary",

        onResults: function (result) {
            var data = result.data || {};

            // Overall stats
            setField(resOverallMin,     data.overall_min_balance);
            setField(resOverallMax,     data.overall_max_balance);
            setField(resOverallClosing, data.overall_closing_balance);

            // Monthly breakdown
            var monthly = data.monthly_summaries || [];
            if (monthly.length) {
                var mHtml = "<table class='summary-table'><thead><tr>" +
                    "<th>Month</th><th>Min Balance</th><th>Max Balance</th><th>Closing Balance</th>" +
                    "</tr></thead><tbody>";
                for (var i = 0; i < monthly.length; i++) {
                    var m = monthly[i];
                    mHtml += "<tr>" +
                        "<td>" + (m.month           || "—") + "</td>" +
                        "<td>" + (m.min_balance      || "—") + "</td>" +
                        "<td>" + (m.max_balance      || "—") + "</td>" +
                        "<td>" + (m.closing_balance  || "—") + "</td>" +
                        "</tr>";
                }
                mHtml += "</tbody></table>";
                resMonthlyTable.innerHTML = mHtml;
            } else {
                resMonthlyTable.textContent = "No monthly data found.";
            }

            // Daily breakdown
            var daily = data.daily_summaries || [];
            if (daily.length) {
                var dHtml = "<table class='summary-table'><thead><tr>" +
                    "<th>Date</th><th>Min Balance</th><th>Max Balance</th><th>Closing Balance</th>" +
                    "</tr></thead><tbody>";
                for (var j = 0; j < daily.length; j++) {
                    var d = daily[j];
                    dHtml += "<tr>" +
                        "<td>" + (d.date            || "—") + "</td>" +
                        "<td>" + (d.min_balance      || "—") + "</td>" +
                        "<td>" + (d.max_balance      || "—") + "</td>" +
                        "<td>" + (d.closing_balance  || "—") + "</td>" +
                        "</tr>";
                }
                dHtml += "</tbody></table>";
                resDailyTable.innerHTML = dHtml;
            } else {
                resDailyTable.textContent = "No daily data found.";
            }
        },

        onReset: function () {
            setField(resOverallMin,     null);
            setField(resOverallMax,     null);
            setField(resOverallClosing, null);
            resMonthlyTable.innerHTML = "—";
            resDailyTable.innerHTML   = "—";
        }
    });

});