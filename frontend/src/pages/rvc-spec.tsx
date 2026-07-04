import { AppLayout } from "@/components/app-layout";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { BookOpen, Download, ExternalLink, FileText, Info, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

interface SpecSection {
  title: string;
  content: string;
  page?: number;
  section?: string;
}

export default function RVCSpec() {
  const [specContent, setSpecContent] = useState<string>("");
  const [specLoading, setSpecLoading] = useState(false);
  const [specError, setSpecError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SpecSection[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Load RV-C specification content
  const loadSpecContent = async () => {
    setSpecLoading(true);
    setSpecError(null);

    try {
      const response = await fetch("/api/config/spec");

      if (!response.ok) {
        throw new Error(`Failed to load specification: ${response.statusText}`);
      }

      const content = await response.text();
      setSpecContent(content);
    } catch (error) {
      setSpecError(error instanceof Error ? error.message : "Failed to load specification");
    } finally {
      setSpecLoading(false);
    }
  };

  // Download the specification — uses the loaded content when available,
  // otherwise fetches it from the backend so the button always works.
  const downloadSpec = async () => {
    try {
      let content = specContent;
      if (!content) {
        const response = await fetch("/api/config/spec");
        if (!response.ok) {
          throw new Error(`Failed to download specification: ${response.statusText}`);
        }
        content = await response.text();
      }
      const blob = new Blob([content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "rvc-specification.txt";
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error("Download failed", {
        description: error instanceof Error ? error.message : "Could not fetch the specification.",
      });
    }
  };

  // Search within the specification content
  const searchSpec = () => {
    if (!searchQuery.trim() || !specContent) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);

    // Simple text search within the spec content
    // In a real implementation, this could use the vector search API
    const lines = specContent.split('\n');
    const results: SpecSection[] = [];
    const queryLower = searchQuery.toLowerCase();

    let currentSection = '';
    let currentContent = '';
    let lineNumber = 0;

    for (const line of lines) {
      lineNumber++;

      // Detect section headers (lines starting with # or numbers/letters followed by periods)
      if (line.match(/^#+\s+/) || line.match(/^\d+\.\d*\s+/) || line.match(/^[A-Z]\.\s+/)) {
        // Save previous section if it had matches
        if (currentContent && currentContent.toLowerCase().includes(queryLower)) {
          results.push({
            title: currentSection || 'Untitled Section',
            content: currentContent.substring(0, 300) + (currentContent.length > 300 ? '...' : ''),
            page: Math.floor(lineNumber / 50) + 1, // Rough page estimate
            section: currentSection
          });
        }

        currentSection = line.replace(/^#+\s+/, '').replace(/^\d+\.\d*\s+/, '').replace(/^[A-Z]\.\s+/, '');
        currentContent = '';
      } else {
        currentContent += line + '\n';
      }

      // Also check for direct line matches
      if (line.toLowerCase().includes(queryLower) && !results.some(r => r.content.includes(line))) {
        results.push({
          title: currentSection || `Line ${lineNumber}`,
          content: line + '\n' + lines.slice(lineNumber, lineNumber + 2).join('\n'),
          page: Math.floor(lineNumber / 50) + 1,
          section: currentSection
        });
      }
    }

    // Limit results and sort by relevance (simple scoring based on query frequency)
    const scoredResults = results
      .map(result => ({
        ...result,
        score: (result.content.toLowerCase().match(new RegExp(queryLower, 'g')) || []).length
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 10);

    setSearchResults(scoredResults);
    setIsSearching(false);
  };

  // Load spec content on component mount
  useEffect(() => {
    void loadSpecContent();
  }, []);

  return (
    <AppLayout>
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Header (title comes from the app shell) */}
        <div>
          <p className="text-muted-foreground">
            Access and search the comprehensive Recreational Vehicle Controller Area Network specification
          </p>
        </div>

        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList>
            <TabsTrigger value="overview">
              <Info className="mr-2 h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="search">
              <Search className="mr-2 h-4 w-4" />
              Search
            </TabsTrigger>
            <TabsTrigger value="content">
              <FileText className="mr-2 h-4 w-4" />
              Full Specification
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2">
              {/* About RV-C */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BookOpen className="h-5 w-5" />
                    About RV-C
                  </CardTitle>
                  <CardDescription>
                    Understanding the Recreational Vehicle Controller Area Network
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="text-sm space-y-3">
                    <p>
                      RV-C (Recreational Vehicle Controller Area Network) is a standardized
                      communication protocol designed specifically for recreational vehicles.
                    </p>
                    <p>
                      It defines how various systems in an RV communicate with each other
                      over a CAN bus network, including:
                    </p>
                    <ul className="space-y-1 ml-4">
                      <li>• Lighting systems</li>
                      <li>• Tank monitoring</li>
                      <li>• Climate control</li>
                      <li>• Power management</li>
                      <li>• Safety systems</li>
                      <li>• Engine and drivetrain</li>
                    </ul>
                  </div>
                </CardContent>
              </Card>

              {/* Specification Access */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Download className="h-5 w-5" />
                    Specification Access
                  </CardTitle>
                  <CardDescription>
                    Download and access the current RV-C specification
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Button
                      className="w-full justify-start"
                      variant="outline"
                      onClick={() => window.open("/api/config/spec", "_blank")}
                      disabled={specLoading}
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View Raw Specification
                    </Button>
                    <Button
                      className="w-full justify-start"
                      variant="outline"
                      onClick={() => void downloadSpec()}
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Download Specification
                    </Button>
                  </div>
                  <Separator />
                  <div className="text-sm text-muted-foreground">
                    <p>The specification includes:</p>
                    <ul className="mt-2 space-y-1 ml-4">
                      <li>• Data Group Number (DGN) definitions</li>
                      <li>• Parameter specifications</li>
                      <li>• Message formats and timing</li>
                      <li>• Device addressing schemes</li>
                      <li>• Implementation guidelines</li>
                    </ul>
                  </div>
                </CardContent>
              </Card>

              {/* Key Concepts */}
              <Card>
                <CardHeader>
                  <CardTitle>Key RV-C Concepts</CardTitle>
                  <CardDescription>
                    Important terms and concepts in RV-C
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">DGN</Badge>
                        <span className="font-medium">Data Group Number</span>
                      </div>
                      <p className="text-sm text-muted-foreground ml-16">
                        Unique identifier for specific data types (e.g., lighting commands, tank levels)
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">PGN</Badge>
                        <span className="font-medium">Parameter Group Number</span>
                      </div>
                      <p className="text-sm text-muted-foreground ml-16">
                        CAN bus identifier that includes DGN and priority information
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">Instance</Badge>
                        <span className="font-medium">Device Instance</span>
                      </div>
                      <p className="text-sm text-muted-foreground ml-16">
                        Distinguishes between multiple devices of the same type
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">SA</Badge>
                        <span className="font-medium">Source Address</span>
                      </div>
                      <p className="text-sm text-muted-foreground ml-16">
                        Unique address identifying the device sending the message
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Implementation Status */}
              <Card>
                <CardHeader>
                  <CardTitle>Implementation Status</CardTitle>
                  <CardDescription>
                    Current support in CoachIQ
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Message Decoding</span>
                      <Badge variant="default">✓ Supported</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Entity Mapping</span>
                      <Badge variant="default">✓ Supported</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Device Control</span>
                      <Badge variant="default">✓ Supported</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Unknown PGN Detection</span>
                      <Badge variant="default">✓ Supported</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Specification Search</span>
                      <Badge variant="default">✓ Supported</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Search Tab */}
          <TabsContent value="search" className="space-y-6">
            {/* Search Interface */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Search className="h-5 w-5" />
                  Specification Search
                </CardTitle>
                <CardDescription>
                  Search within the RV-C specification content for specific terms, DGNs, or concepts
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Input
                    placeholder="Search specification... (e.g., 'DGN 1FECA', 'lighting', 'tank level')"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && searchSpec()}
                    className="flex-1"
                  />
                  <Button onClick={searchSpec} disabled={isSearching || !searchQuery.trim()}>
                    {isSearching ? "Searching..." : "Search"}
                  </Button>
                </div>

                {/* Quick Search Buttons */}
                <div className="flex flex-wrap gap-2">
                  {[
                    "DGN 1FECA", // DC Load Command
                    "DGN 1FFFF", // AC Load Command
                    "DGN 1FFB7", // Tank Status
                    "DGN 1FEF7", // Temperature
                    "Instance",
                    "Source Address",
                  ].map((term) => (
                    <Button
                      key={term}
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setSearchQuery(term);
                        setTimeout(searchSpec, 100);
                      }}
                    >
                      {term}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">
                  Search Results ({searchResults.length})
                </h3>
                {searchResults.map((result, index) => (
                  <Card key={index}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1 flex-1">
                          <CardTitle className="text-base">
                            {result.title}
                          </CardTitle>
                          {result.section && (
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              <FileText className="h-3 w-3" />
                              <span>Section: {result.section}</span>
                              {result.page && (
                                <>
                                  <span>•</span>
                                  <span>Page ~{result.page}</span>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <pre className="text-sm text-muted-foreground whitespace-pre-wrap font-mono bg-muted p-3 rounded-md overflow-x-auto">
                        {result.content}
                      </pre>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {searchQuery && !isSearching && searchResults.length === 0 && (
              <Card>
                <CardContent className="text-center py-8">
                  <p className="text-muted-foreground">
                    No results found for "{searchQuery}"
                  </p>
                  <p className="text-sm text-muted-foreground mt-2">
                    Try searching for DGN numbers, device types, or specification sections
                  </p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Full Specification Tab */}
          <TabsContent value="content" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Full RV-C Specification
                </CardTitle>
                <CardDescription>
                  Complete specification content loaded from the server
                </CardDescription>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void loadSpecContent()}
                    disabled={specLoading}
                  >
                    {specLoading ? "Loading..." : "Reload"}
                  </Button>
                  {specContent && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void downloadSpec()}
                    >
                      <Download className="mr-2 h-3 w-3" />
                      Download
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {specLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-4 w-2/3" />
                  </div>
                ) : specError ? (
                  <Alert variant="destructive">
                    <AlertDescription>{specError}</AlertDescription>
                  </Alert>
                ) : specContent ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-muted-foreground">
                        Specification content ({specContent.length.toLocaleString()} characters)
                      </p>
                      <Badge variant="outline">
                        ~{Math.ceil(specContent.split('\n').length / 50)} pages
                      </Badge>
                    </div>
                    <Textarea
                      value={specContent}
                      readOnly
                      className="min-h-[600px] font-mono text-sm resize-none"
                      placeholder="Loading specification content..."
                    />
                  </div>
                ) : (
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertDescription>
                      Click "Reload" to load the RV-C specification content from the server.
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
