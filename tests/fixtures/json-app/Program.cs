using Newtonsoft.Json;

internal static class Program
{
    private static void Main()
    {
        var payload = JsonConvert.SerializeObject(new { name = "ACCRa" });
        System.Console.WriteLine(payload);
    }
}
