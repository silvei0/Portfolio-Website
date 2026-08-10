(() => {
    "use strict";

    const projectsNav = document.querySelector(".projects-page nav");

    if (projectsNav) {
        let navUpdateFrame = null;
        let lastNavOpacity = null;

        const updateProjectsNav = () => {
            const opacity = Math.min(window.scrollY / 250, 1) * 0.72;
            if (opacity !== lastNavOpacity) {
                projectsNav.style.setProperty("--projects-nav-opacity", opacity);
                lastNavOpacity = opacity;
            }
            navUpdateFrame = null;
        };

        window.addEventListener("scroll", () => {
            if (navUpdateFrame === null) navUpdateFrame = requestAnimationFrame(updateProjectsNav);
        }, { passive: true });
        updateProjectsNav();
    }

    const archiveRoot = document.querySelector("[data-project-archive]");
    if (!archiveRoot) return;

    const isAllProjectsPage = archiveRoot.hasAttribute("data-all-projects");
    const manifestSource = archiveRoot.dataset.projectsSource || "./projects.json";
    const listElements = new Map(
        [...archiveRoot.querySelectorAll("[data-project-list]")]
            .map(element => [element.dataset.projectList, element])
    );
    const filterElements = [...archiveRoot.querySelectorAll("[data-project-filter]")];
    const clearFiltersButton = archiveRoot.querySelector("[data-clear-project-filters]");
    const projectCount = archiveRoot.querySelector("[data-project-count]");
    const projectDateFormatter = new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC"
    });

    const hasText = value => value !== undefined
        && value !== null
        && String(value).trim() !== "";

    const slugify = value => String(value || "")
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");

    const normaliseFolder = entry => {
        const value = typeof entry === "string" ? entry : entry?.folder;
        if (!hasText(value)) return null;

        const folder = String(value).trim().replace(/^\.\//, "").replace(/\/$/, "");
        if (!/^[a-z0-9][a-z0-9-]*$/i.test(folder)) {
            console.warn(`Projects archive: skipped unsafe folder name "${value}".`);
            return null;
        }
        return folder;
    };

    const getTimestamp = date => {
        if (!hasText(date)) return Number.NEGATIVE_INFINITY;
        const timestamp = Date.parse(String(date));
        return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
    };

    const formatDate = date => {
        const timestamp = getTimestamp(date);
        if (!Number.isFinite(timestamp)) return "Undated";
        return projectDateFormatter.format(new Date(timestamp));
    };

    const formatUpdateDate = date => {
        const timestamp = getTimestamp(date);
        if (!Number.isFinite(timestamp)) return "—";
        const value = new Date(timestamp);
        const day = String(value.getUTCDate()).padStart(2, "0");
        const month = String(value.getUTCMonth() + 1).padStart(2, "0");
        const year = String(value.getUTCFullYear()).slice(-2);
        return `${day}/${month}/${year}`;
    };

    const createElement = (tag, className, text) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = String(text);
        return element;
    };

    const getDescription = project => {
        const description = project.archive?.cardDescription || project.description || project.metaDescription;
        if (Array.isArray(description)) return description.find(hasText) || "";
        return hasText(description) ? String(description) : "";
    };

    const renderTags = (tags, className) => {
        if (!Array.isArray(tags)) return null;
        const values = [...new Set(tags.filter(hasText).map(tag => String(tag).trim()))].slice(0, 8);
        if (!values.length) return null;

        const wrapper = createElement("div", className);
        wrapper.setAttribute("aria-label", "Project tags");
        values.forEach(tag => wrapper.append(createElement("span", "project-tag", tag)));
        return wrapper;
    };

    const resolveMediaUrl = (path, jsonUrl) => {
        if (!hasText(path)) return null;
        try {
            return new URL(String(path), jsonUrl).href;
        } catch (error) {
            console.warn("Projects archive: skipped an invalid media path.", path, error);
            return null;
        }
    };

    const appendThumbnail = (card, project) => {
        const thumbnail = project.archive?.thumbnail || project.hero || {};
        const source = resolveMediaUrl(thumbnail.src, project.jsonUrl);

        if (source) {
            const image = createElement("img", "post-thumbnail project-card-thumbnail");
            image.src = source;
            image.alt = thumbnail.decorative === true
                ? ""
                : thumbnail.alt || project.hero?.alt || `${project.title} project thumbnail`;
            image.loading = "lazy";
            image.decoding = "async";
            if (hasText(thumbnail.width)) image.width = Number(thumbnail.width);
            if (hasText(thumbnail.height)) image.height = Number(thumbnail.height);
            card.append(image);
            return;
        }

        const placeholder = createElement(
            "div",
            "post-thumbnail project-card-placeholder",
            thumbnail.placeholder || "Project preview"
        );
        placeholder.setAttribute("role", "img");
        placeholder.setAttribute("aria-label", thumbnail.alt || `${project.title} project preview`);
        card.append(placeholder);
    };

    const createProjectCard = project => {
        const card = createElement("a", "post-card project-card");
        card.href = project.projectUrl;
        appendThumbnail(card, project);

        card.append(createElement("h3", "project-card-title", project.title || "Untitled project"));

        const description = getDescription(project);
        if (description) card.append(createElement("p", "project-card-description", description));

        const tags = renderTags(project.tags, "project-card-tags");
        if (tags) card.append(tags);

        const meta = createElement("div", "project-card-meta");
        const time = createElement("time", "project-card-date", formatDate(project.archive.date));
        if (hasText(project.archive.date)) time.setAttribute("datetime", project.archive.date);
        meta.append(time);
        if (hasText(project.status)) {
            const statusClass = slugify(project.status);
            meta.append(createElement(
                "span",
                `project-card-status${statusClass ? ` project-card-status--${statusClass}` : ""}`,
                project.status
            ));
        }
        card.append(meta);

        return card;
    };

    const TYPE_FILTER_ALIASES = {
        "civil-engineering": ["civil-engineering", "civil"],
        gis: ["gis", "geographic-information-systems"],
        "cad-bim": ["cad-bim", "cad", "bim"],
        design: ["design"],
        personal: ["personal", "personal-project"]
    };
    const NAMED_TOOL_FILTERS = ["autocad", "civil-3d", "revit", "qgis", "excel", "fusion-360"];

    const normaliseFilterValues = value => {
        const values = Array.isArray(value) ? value : [value];
        return values.filter(hasText).map(item => slugify(item)).filter(Boolean);
    };

    const valueMatchesAlias = (value, alias) => value === alias
        || value.startsWith(`${alias}-`)
        || value.endsWith(`-${alias}`)
        || value.includes(`-${alias}-`);

    const matchesYear = (project, selectedYear) => {
        if (selectedYear === "all") return true;
        const match = String(project.archive.date || "").match(/^(\d{4})/);
        if (!match) return false;
        const year = Number(match[1]);
        return selectedYear === "earlier" ? year < 2025 : year === Number(selectedYear);
    };

    const matchesType = (project, selectedType) => {
        if (selectedType === "all") return true;
        const values = normaliseFilterValues([
            project.projectType,
            project.discipline,
            ...(Array.isArray(project.tags) ? project.tags : [])
        ]);
        const aliases = TYPE_FILTER_ALIASES[selectedType] || [selectedType];
        return values.some(value => aliases.some(alias => valueMatchesAlias(value, alias)));
    };

    const matchesTool = (project, selectedTool) => {
        if (selectedTool === "all") return true;
        const tools = normaliseFilterValues(project.tools);
        if (selectedTool === "other") {
            return tools.some(tool => !NAMED_TOOL_FILTERS.some(named => valueMatchesAlias(tool, named)));
        }
        return tools.some(tool => valueMatchesAlias(tool, selectedTool));
    };

    const matchesStatus = (project, selectedStatus) => {
        if (selectedStatus === "all") return true;
        const status = slugify(project.status);
        if (selectedStatus === "completed") {
            return ["complete", "completed", "finished"].some(value => valueMatchesAlias(status, value));
        }
        if (selectedStatus === "in-progress") {
            return project.archive.currentlyWorking === true
                || ["in-progress", "ongoing"].some(value => valueMatchesAlias(status, value));
        }
        return false;
    };

    const matchesFilters = (project, filters) => matchesYear(project, filters.year)
        && matchesType(project, filters.type)
        && matchesTool(project, filters.tool)
        && matchesStatus(project, filters.status);

    const renderFilterableProjects = projects => {
        const element = listElements.get("filtered");
        if (!element) return;

        const cardEntries = projects.map(project => ({
            project,
            card: createProjectCard(project),
            hideTimer: null
        }));
        const fragment = document.createDocumentFragment();
        cardEntries.forEach(entry => fragment.append(entry.card));
        const noMatches = createElement("p", "projects-empty all-projects-empty", "No projects match these filters.");
        noMatches.hidden = true;
        fragment.append(noMatches);
        element.replaceChildren(fragment);
        element.removeAttribute("aria-busy");

        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const transitionDuration = reducedMotion ? 0 : 180;

        const setCardVisibility = (entry, visible) => {
            if (entry.hideTimer !== null) {
                window.clearTimeout(entry.hideTimer);
                entry.hideTimer = null;
            }

            if (visible) {
                if (entry.card.hidden) {
                    entry.card.hidden = false;
                    entry.card.classList.add("is-filtered-out");
                    requestAnimationFrame(() => requestAnimationFrame(() => {
                        entry.card.classList.remove("is-filtered-out");
                    }));
                } else {
                    entry.card.classList.remove("is-filtered-out");
                }
                entry.card.removeAttribute("aria-hidden");
                return;
            }

            entry.card.classList.add("is-filtered-out");
            entry.card.setAttribute("aria-hidden", "true");
            entry.hideTimer = window.setTimeout(() => {
                if (entry.card.classList.contains("is-filtered-out")) entry.card.hidden = true;
                entry.hideTimer = null;
            }, transitionDuration);
        };

        const readFilters = () => Object.fromEntries(
            filterElements.map(filter => [filter.dataset.projectFilter, filter.value])
        );

        const applyFilters = () => {
            const filters = {
                year: "all",
                type: "all",
                tool: "all",
                status: "all",
                ...readFilters()
            };
            let visibleCount = 0;
            cardEntries.forEach(entry => {
                const visible = matchesFilters(entry.project, filters);
                if (visible) visibleCount += 1;
                setCardVisibility(entry, visible);
            });

            const filtersActive = Object.values(filters).some(value => value !== "all");
            if (clearFiltersButton) clearFiltersButton.hidden = !filtersActive;
            if (projectCount) projectCount.textContent = `${visibleCount} ${visibleCount === 1 ? "project" : "projects"}`;

            noMatches.textContent = projects.length
                ? "No projects match these filters."
                : "No public projects have been published yet.";
            noMatches.hidden = visibleCount !== 0;
        };

        filterElements.forEach(filter => filter.addEventListener("change", applyFilters));
        clearFiltersButton?.addEventListener("click", () => {
            filterElements.forEach(filter => {
                filter.value = "all";
            });
            applyFilters();
            filterElements[0]?.focus();
        });
        applyFilters();
    };

    const showListMessage = (element, message, isError = false) => {
        if (!element) return;
        const paragraph = createElement("p", isError ? "projects-empty projects-error" : "projects-empty", message);
        element.replaceChildren(paragraph);
        element.removeAttribute("aria-busy");
    };

    const renderCards = (name, projects, emptyMessage) => {
        const element = listElements.get(name);
        if (!element) return;
        if (!projects.length) {
            showListMessage(element, emptyMessage);
            return;
        }

        const fragment = document.createDocumentFragment();
        projects.forEach(project => fragment.append(createProjectCard(project)));
        element.replaceChildren(fragment);
        element.removeAttribute("aria-busy");
    };

    const renderUpdates = updates => {
        const element = listElements.get("updates");
        if (!element) return;
        if (!updates.length) {
            showListMessage(element, "No public project updates yet.");
            return;
        }

        const fragment = document.createDocumentFragment();
        updates.forEach(item => {
            const update = createElement("div", "update-item");
            const time = createElement("time", "update-date", formatUpdateDate(item.date));
            if (hasText(item.date)) time.setAttribute("datetime", item.date);
            update.append(time, createElement("p", "update-text", item.content));
            fragment.append(update);
        });
        element.replaceChildren(fragment);
        element.removeAttribute("aria-busy");
    };

    const sortNewestFirst = (left, right) => {
        const leftTimestamp = getTimestamp(left.archive.date);
        const rightTimestamp = getTimestamp(right.archive.date);
        if (leftTimestamp !== rightTimestamp) {
            if (!Number.isFinite(leftTimestamp)) return 1;
            if (!Number.isFinite(rightTimestamp)) return -1;
            return rightTimestamp - leftTimestamp;
        }
        return String(left.title || "").localeCompare(String(right.title || ""));
    };

    const loadProject = async (folder, manifestUrl) => {
        const jsonUrl = new URL(`${folder}/project.json`, manifestUrl);
        const response = await fetch(jsonUrl, { cache: "no-cache" });
        if (!response.ok) throw new Error(`${folder}/project.json returned HTTP ${response.status}`);

        const project = await response.json();
        if (!project || typeof project !== "object" || Array.isArray(project)) {
            throw new Error(`${folder}/project.json must contain one JSON object`);
        }

        const archive = project.archive && typeof project.archive === "object"
            ? project.archive
            : {};

        return {
            ...project,
            archive,
            folder,
            jsonUrl: response.url,
            projectUrl: new URL(`${folder}/`, manifestUrl).href
        };
    };

    const sortUpdatesNewestFirst = (left, right) => {
        const leftTimestamp = getTimestamp(left.date);
        const rightTimestamp = getTimestamp(right.date);
        if (leftTimestamp !== rightTimestamp) {
            if (!Number.isFinite(leftTimestamp)) return 1;
            if (!Number.isFinite(rightTimestamp)) return -1;
            return rightTimestamp - leftTimestamp;
        }
        return String(left.content || "").localeCompare(String(right.content || ""));
    };

    const prepareUpdates = (entries, publicProjects) => {
        if (!Array.isArray(entries)) {
            return publicProjects.slice(0, 3).map(project => ({
                date: project.archive.date,
                content: project.title || "Untitled project"
            }));
        }

        return entries.map(entry => {
            if (!entry || typeof entry !== "object") return null;
            if (String(entry.visibility || "public").toLowerCase() !== "public") return null;

            const content = entry.content || entry.description || entry.title;
            if (!hasText(content)) {
                console.warn("Projects archive: an update without body content was skipped.");
                return null;
            }

            return {
                date: entry.date,
                content: String(content)
            };
        }).filter(Boolean).sort(sortUpdatesNewestFirst);
    };

    const renderArchive = (projects, updateEntries) => {
        const publicProjects = projects
            .filter(project => String(project.archive.visibility || "private").toLowerCase() === "public")
            .sort(sortNewestFirst);

        if (isAllProjectsPage) {
            renderFilterableProjects(publicProjects);
            document.dispatchEvent(new CustomEvent("projects:rendered", {
                detail: {
                    all: projects.length,
                    public: publicProjects.length,
                    private: projects.length - publicProjects.length
                }
            }));
            return;
        }

        const workingProjects = publicProjects.filter(project => {
            if (typeof project.archive.currentlyWorking === "boolean") {
                return project.archive.currentlyWorking;
            }
            return String(project.status || "").trim().toLowerCase() === "in progress";
        });
        const featuredProjects = publicProjects.filter(project => project.archive.featured === true);
        const recentProjects = publicProjects.slice(0, 3);
        const updates = prepareUpdates(updateEntries, publicProjects);

        renderUpdates(updates);
        renderCards("working", workingProjects, "No public projects are currently marked as in progress.");
        renderCards("recent", recentProjects, "No public projects have been published yet.");
        renderCards("featured", featuredProjects, "No public projects are featured yet.");
        renderCards("all", publicProjects, "No public projects have been published yet.");

        document.dispatchEvent(new CustomEvent("projects:rendered", {
            detail: {
                all: projects.length,
                public: publicProjects.length,
                private: projects.length - publicProjects.length
            }
        }));
    };

    const showArchiveError = error => {
        console.error(`Projects archive: failed to load ${manifestSource}.`, error);
        if (projectCount) projectCount.textContent = "Projects unavailable";
        listElements.forEach(element => {
            showListMessage(element, "Projects could not be loaded. Check projects.json and each project folder.", true);
        });
    };

    const loadArchive = async () => {
        try {
            const response = await fetch(manifestSource, { cache: "no-cache" });
            if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);

            const manifest = await response.json();
            const entries = Array.isArray(manifest) ? manifest : manifest.projects;
            if (!Array.isArray(entries)) throw new Error("projects.json must contain a projects array");

            const folders = [...new Set(entries.map(normaliseFolder).filter(Boolean))];
            const results = await Promise.allSettled(
                folders.map(folder => loadProject(folder, response.url))
            );

            const projects = [];
            results.forEach(result => {
                if (result.status === "fulfilled") projects.push(result.value);
                else console.warn("Projects archive: one project was skipped.", result.reason);
            });
            renderArchive(projects, Array.isArray(manifest) ? undefined : manifest.updates);
        } catch (error) {
            showArchiveError(error);
        }
    };

    loadArchive();
})();
