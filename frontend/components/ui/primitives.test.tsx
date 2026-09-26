import { useState, type ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Combobox, ComboboxAnchor, ComboboxContent, ComboboxInput, ComboboxItem, ComboboxList } from "@/components/ui/combobox";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverStub;
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.HTMLElement.prototype.hasPointerCapture = () => false;
  window.HTMLElement.prototype.setPointerCapture = () => {};
  window.HTMLElement.prototype.releasePointerCapture = () => {};
});

afterEach(() => {
  cleanup();
});

function user() {
  return userEvent.setup();
}

describe("Button", () => {
  it("activates from the keyboard", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    const control = screen.getByRole("button", { name: "Go" });
    control.focus();
    await user().keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("Input", () => {
  it("accepts typed text", async () => {
    render(<Input aria-label="Name" />);
    const field = screen.getByRole("textbox", { name: "Name" });
    await user().type(field, "Ada");
    expect(field).toHaveProperty("value", "Ada");
  });
});

describe("Textarea", () => {
  it("accepts typed text", async () => {
    render(<Textarea aria-label="Note" />);
    const field = screen.getByRole("textbox", { name: "Note" });
    await user().type(field, "Hi");
    expect(field).toHaveProperty("value", "Hi");
  });
});

describe("Badge and Kbd", () => {
  it("renders the label", () => {
    render(
      <>
        <Badge>Info</Badge>
        <Kbd>Esc</Kbd>
      </>
    );
    expect(screen.getByText("Info").textContent).toBe("Info");
    expect(screen.getByText("Esc").textContent).toBe("Esc");
  });
});

describe("ScrollArea", () => {
  it("renders its children", () => {
    render(
      <ScrollArea>
        <p>Inside</p>
      </ScrollArea>
    );
    expect(screen.getByText("Inside").textContent).toBe("Inside");
  });
});

describe("Dialog", () => {
  it("closes with Escape and returns focus", async () => {
    render(
      <Dialog>
        <DialogTrigger>Open dialog</DialogTrigger>
        <DialogContent>
          <DialogTitle>Hello</DialogTitle>
        </DialogContent>
      </Dialog>
    );
    const trigger = screen.getByRole("button", { name: "Open dialog" });
    await user().click(trigger);
    expect(screen.getByRole("dialog")).toBeTruthy();
    await user().keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("AlertDialog", () => {
  it("closes with Escape and returns focus", async () => {
    render(
      <AlertDialog>
        <AlertDialogTrigger>Open alert</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogTitle>Confirm</AlertDialogTitle>
        </AlertDialogContent>
      </AlertDialog>
    );
    const trigger = screen.getByRole("button", { name: "Open alert" });
    await user().click(trigger);
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    await user().keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("DropdownMenu", () => {
  it("moves with arrows, closes with Escape, and returns focus", async () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>One</DropdownMenuItem>
          <DropdownMenuItem>Two</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
    const actor = user();
    const trigger = screen.getByRole("button", { name: "Menu" });
    await actor.click(trigger);
    expect(screen.getByRole("menu")).toBeTruthy();
    await actor.keyboard("{ArrowDown}{ArrowDown}");
    expect(document.activeElement?.textContent).toContain("Two");
    await actor.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("Popover", () => {
  it("closes with Escape and returns focus", async () => {
    render(
      <Popover>
        <PopoverTrigger>Open popover</PopoverTrigger>
        <PopoverContent>Panel</PopoverContent>
      </Popover>
    );
    const trigger = screen.getByRole("button", { name: "Open popover" });
    await user().click(trigger);
    expect(screen.getByText("Panel")).toBeTruthy();
    await user().keyboard("{Escape}");
    expect(screen.queryByText("Panel")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("Tooltip", () => {
  it("shows on focus and hides with Escape", async () => {
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip content="Hint">
          <button type="button">Tip</button>
        </Tooltip>
      </TooltipProvider>
    );
    const trigger = screen.getByRole("button", { name: "Tip" });
    trigger.focus();
    expect(await screen.findByRole("tooltip")).toBeTruthy();
    await user().keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});

describe("Tabs", () => {
  it("moves selection with the arrow keys", async () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Alpha</TabsTrigger>
          <TabsTrigger value="b">Beta</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Alpha panel</TabsContent>
        <TabsContent value="b">Beta panel</TabsContent>
      </Tabs>
    );
    screen.getByRole("tab", { name: "Alpha" }).focus();
    await user().keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Beta" }).getAttribute("data-state")).toBe("active");
    expect(screen.getByText("Beta panel")).toBeTruthy();
  });
});

describe("Select", () => {
  it("opens, moves with arrows, and closes with Escape", async () => {
    render(
      <Select>
        <SelectTrigger aria-label="Pick">
          <SelectValue placeholder="Choose" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="alpha">Alpha</SelectItem>
          <SelectItem value="beta">Beta</SelectItem>
        </SelectContent>
      </Select>
    );
    const trigger = screen.getByRole("combobox", { name: "Pick" });
    await user().click(trigger);
    expect(screen.getByRole("listbox")).toBeTruthy();
    await user().keyboard("{ArrowDown}");
    expect(document.activeElement?.textContent).toContain("Beta");
    await user().keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

function FilterCombobox({ children }: { children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Combobox open={open} onOpenChange={setOpen}>
      <ComboboxAnchor asChild>
        <button type="button" aria-haspopup="listbox" onClick={() => setOpen((value) => !value)}>
          {children ?? "Pick member"}
        </button>
      </ComboboxAnchor>
      <ComboboxContent>
        <ComboboxInput aria-label="Search" />
        <ComboboxList>
          <ComboboxItem value="alpha">Alpha</ComboboxItem>
          <ComboboxItem value="beta">Beta</ComboboxItem>
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

describe("Combobox", () => {
  it("keeps an anchor aria-haspopup of listbox", () => {
    render(<FilterCombobox>—</FilterCombobox>);
    expect(screen.getByRole("button", { name: "—" }).getAttribute("aria-haspopup")).toBe("listbox");
  });

  it("filters, moves with arrows, closes with Escape, and returns focus", async () => {
    const actor = user();
    render(<FilterCombobox />);
    const trigger = screen.getByRole("button", { name: "Pick member" });
    await actor.click(trigger);
    const search = screen.getByRole("combobox");
    await actor.click(search);
    await actor.type(search, "al");
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.queryByText("Beta")).toBeNull();
    await actor.keyboard("{ArrowDown}");
    expect(document.querySelector("[data-selected='true']")?.textContent).toContain("Alpha");
    await actor.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("toggles closed when the anchor is clicked again", async () => {
    const actor = user();
    render(<FilterCombobox />);
    const trigger = screen.getByRole("button", { name: "Pick member" });
    await actor.click(trigger);
    expect(screen.getByRole("listbox")).toBeTruthy();
    await actor.click(trigger);
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("ToggleGroup", () => {
  it("moves the pressed item with the arrow keys", async () => {
    render(
      <ToggleGroup type="single" defaultValue="a">
        <ToggleGroupItem value="a">Left</ToggleGroupItem>
        <ToggleGroupItem value="b">Right</ToggleGroupItem>
      </ToggleGroup>
    );
    const actor = user();
    const right = screen.getByRole("radio", { name: "Right" });
    screen.getByRole("radio", { name: "Left" }).focus();
    await actor.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(right);
    await actor.keyboard(" ");
    expect(right.getAttribute("data-state")).toBe("on");
  });
});
