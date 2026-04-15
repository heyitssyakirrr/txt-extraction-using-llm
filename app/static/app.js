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
            var existing = warnMessage.textContent;
            warnMessage.textContent = existing ? existing + " " + msg : msg;
            warnBanner.classList.add("visible");
        }

        function hideBanners() {
            errorBanner.classList.remove("visible");
            warnBanner.classList.remove("visible");
            warnMessage.textContent = "";
            errorMessage.textContent = "";
        }

        return { showWarn: showWarn };
    }

    // -------------------------------------------------------------------------
    // SHARED FIELD HELPER
    // -------------------------------------------------------------------------
    function getExtractedValue(result, key) {
        // Primary source: result.data (the ExtractionResult fields)
        if (result && result.data && result.data[key] != null && result.data[key] !== "") {
            return result.data[key];
        }
        // Fallback: result.comparison[key].extracted (FieldComparisonDetail)
        if (result && result.comparison && result.comparison[key] &&
            result.comparison[key].extracted != null && result.comparison[key].extracted !== "") {
            return result.comparison[key].extracted;
        }
        return null;
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

    // -------------------------------------------------------------------------
    // COMPARISON PANEL RENDERER
    // -------------------------------------------------------------------------
    function renderComparison(comparison) {
        var panel = document.getElementById("comparisonPanel");
        if (!panel) return;

        if (!comparison) {
            panel.innerHTML = "";
            return;
        }

        var FIELD_LABELS = {
            bank_name:             "Bank Name",
            fi_num:                "FI Number",
            master_account_number: "Master Account No.",
            sub_account_number:    "Sub Account No.",
        };

        var html = '<span class="section-label">Verification</span>';

        // Overall badge
        if (!comparison.csv_row_found) {
            html += '<div class="cmp-badge cmp-badge--warn">&#9888; File not found in reference data (key: ' +
                escHtml(comparison.filename_key) + ')</div>';
        } else if (comparison.all_match) {
            html += '<div class="cmp-badge cmp-badge--pass">&#10003; All fields match</div>';
        } else {
            html += '<div class="cmp-badge cmp-badge--fail">&#10007; Mismatch detected</div>';
        }

        // Always render the table — show extracted vs expected for all fields
        var fields = ["bank_name", "fi_num", "master_account_number", "sub_account_number"];
        html += '<div class="cmp-table-wrap"><table class="cmp-table"><thead><tr>' +
            '<th>Field</th><th>Extracted</th><th>Expected</th><th>Status</th>' +
            '</tr></thead><tbody>';

        fields.forEach(function (key) {
            var detail = comparison[key];
            if (!detail) return;

            var statusIcon, statusClass;
            if (!comparison.csv_row_found) {
                statusIcon  = "&#9888;";
                statusClass = "cmp-warn";
            } else {
                statusIcon  = detail.match ? "&#10003;" : "&#10007;";
                statusClass = detail.match ? "cmp-pass" : "cmp-fail";
            }

            html += '<tr class="' + statusClass + '">' +
                '<td class="cmp-field-name">' + FIELD_LABELS[key] + '</td>' +
                '<td>' + escHtml(detail.extracted || "\u2014") + '</td>' +
                '<td>' + escHtml(detail.expected  || "\u2014") + '</td>' +
                '<td class="cmp-status">' + statusIcon + '</td>' +
                '</tr>';
        });

        html += '</tbody></table></div>';
        panel.innerHTML = html;
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // -------------------------------------------------------------------------
    // CUSTOMER DETAIL EXTRACTION WIDGET
    // -------------------------------------------------------------------------
    var resName      = document.getElementById("resName");
    var resMasterAcc = document.getElementById("resMasterAcc");
    var resSubAcc    = document.getElementById("resSubAcc");
    var resAddress   = document.getElementById("resAddress");
    var resFiNum     = document.getElementById("resFiNum");
    var resBankName  = document.getElementById("resBankName");

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
            // Debug: log raw API response to browser console for diagnosis
            console.log("[Extraction] API response:", JSON.stringify(result, null, 2));

            var extractedValues = {
                name:                  getExtractedValue(result, "name"),
                master_account_number: getExtractedValue(result, "master_account_number"),
                sub_account_number:    getExtractedValue(result, "sub_account_number"),
                address:               getExtractedValue(result, "address"),
                fi_num:                getExtractedValue(result, "fi_num"),
                bank_name:             getExtractedValue(result, "bank_name"),
            };

            console.log("[Extraction] Resolved field values:", extractedValues);

            setField(resName,      extractedValues.name);
            setField(resMasterAcc, extractedValues.master_account_number);
            setField(resSubAcc,    extractedValues.sub_account_number);
            setField(resAddress,   extractedValues.address);
            setField(resFiNum,     extractedValues.fi_num);
            setField(resBankName,  extractedValues.bank_name);

            // Render comparison panel first
            renderComparison(result.comparison || null);

            // collect ALL warnings before showing — previously the second
            // showWarn() call silently overwrote the first one.
            var warnings = [];

            var missing = [];
            if (!extractedValues.name)                  missing.push("customer name");
            if (!extractedValues.master_account_number) missing.push("master account number");
            if (!extractedValues.sub_account_number)    missing.push("sub account number");
            if (!extractedValues.address)               missing.push("address");
            if (!extractedValues.fi_num)                missing.push("FI number");
            if (!extractedValues.bank_name)             missing.push("bank name");
            if (missing.length) {
                warnings.push("Could not extract: " + missing.join(", ") + ".");
            }

            if (result.comparison && !result.comparison.csv_row_found) {
                warnings.push(
                    "Reference row not found for file key \u2018" +
                    (result.comparison.filename_key || "unknown") + "\u2019."
                );
            } else if (result.comparison && result.comparison.csv_row_found && !result.comparison.all_match) {
                warnings.push("Reference comparison detected mismatched fields.");
            }

            if (warnings.length) {
                extractWidget.showWarn(warnings.join(" "));
            }
        },

        onReset: function () {
            var fields = [resName, resMasterAcc, resSubAcc, resAddress, resFiNum, resBankName];
            for (var i = 0; i < fields.length; i++) {
                fields[i].textContent = "\u2014";
                fields[i].className   = "field-value";
            }
            var panel = document.getElementById("comparisonPanel");
            if (panel) panel.innerHTML = "";
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
                        "<td>" + (m.month           || "\u2014") + "</td>" +
                        "<td>" + (m.min_balance      || "\u2014") + "</td>" +
                        "<td>" + (m.max_balance      || "\u2014") + "</td>" +
                        "<td>" + (m.closing_balance  || "\u2014") + "</td>" +
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
                        "<td>" + (d.date            || "\u2014") + "</td>" +
                        "<td>" + (d.min_balance      || "\u2014") + "</td>" +
                        "<td>" + (d.max_balance      || "\u2014") + "</td>" +
                        "<td>" + (d.closing_balance  || "\u2014") + "</td>" +
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
            resMonthlyTable.innerHTML = "\u2014";
            resDailyTable.innerHTML   = "\u2014";
        }
    });

});