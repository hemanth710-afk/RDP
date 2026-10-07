
var output = [];
try {
    app.newProject();
    var f = new File("C:/Users/L.Thirumala Teja/Downloads/fragment - slowed - slxughter.mp3");
    var io = new ImportOptions(f);
    io.sequence = false;
    io.forceAlphabetical = false;
    app.beginSuppressDialogs();
    var footage = app.project.importFile(io);
    app.endSuppressDialogs(false);
    output.push("Imported MP3: " + footage.name);
    
    var f2 = new File("C:/Users/L.Thirumala Teja/Downloads/Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4");
    var io2 = new ImportOptions(f2);
    io2.sequence = false;
    io2.forceAlphabetical = false;
    app.beginSuppressDialogs();
    var footage2 = app.project.importFile(io2);
    app.endSuppressDialogs(false);
    output.push("Imported MP4: " + footage2.name);
} catch (e) {
    output.push("Error: " + e.toString());
}
var out = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/scratch/out_seq.txt");
out.open("w");
out.write(output.join("\n"));
out.close();

