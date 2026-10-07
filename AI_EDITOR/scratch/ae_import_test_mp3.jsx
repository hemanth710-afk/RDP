
(function () {
    app.newProject();
    var footageFile = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\fragment - slowed - slxughter.mp3");
    app.beginSuppressDialogs(); // Attempt to suppress
    var importOptions = new ImportOptions(footageFile);
    var footage = app.project.importFile(importOptions);
    app.endSuppressDialogs(false); // End suppression
    $.writeln("MP3 Import successful: " + footage.name);
})();

