(() => {
    "use strict";

    const projectsNav = document.querySelector(".projects-page nav");

    if (projectsNav) {
        const updateProjectsNav = () => {
            const opacity = Math.min(window.scrollY / 250, 1) * 0.72;
            projectsNav.style.setProperty("--projects-nav-opacity", opacity);
        };

        window.addEventListener("scroll", updateProjectsNav, { passive: true });
        updateProjectsNav();
    }

    const archiveRoot = document.querySelector("[data-project-archive]");
    if (!archiveRoot) return;

    const manifestSource = archiveRoot.dataset.projectsSource || "./projects.json";
    const listElements = new Map(
        [...archiveRoot.querySelectorAll("[data-project-list]")]
            .map(element => [element.dataset.projectList, element])
    );

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
        return new Intl.DateTimeFormat("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: "UTC"
        }).format(new Date(timestamp));
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
