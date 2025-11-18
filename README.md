# Onshape-to-WinCNC

A simple python script to convert Onshape CAM Studio .nc files to be compatible with ShopSabre WinCNC.
Brought to you by FRC 7028 Binary Battlion.
---
WARNING: Use at your own risk. Always simulate before executing toolpaths.

Python is required to run the program- you can install it via the microsoft store.

# Preparation

The part you are machining must be in the correct orientation in the part studio it was created in. If you alreayd made the part in the wrong orientation, you can proxy it by creating a new part studio thgat references the original, then transofmr it.

Create a new version of your document to create a snapshot of the part. This is required for Onshape CAM. A CAM Studio will not update automatically when the part is edited in the Part Studio it was created in- it only uses the versioned one. If you need to apply changes to the versioned part in the CAM Studio, you must first create a new version of the document, then update it in the CAM Studio.

---

# CAM Setup

On the bottom bar click the `+` button to create a new tab and select `Create CAM Studio`

1. **Insert your Part**
2. **Create a New Job**
    - A job is one or more operations to be performed on a single part in the same machine. For a sheet part, you will drill the holes and the profile in a single job. For all four sides of a tube, it is still one job- one setup for each side.
    - Give it a descriptive name and select the part as the body. The part name is usually a good name for the job.
3. **Create a Machine**
    - For the ShopSabre 23 CNC Router, select `3-Axis Generic Milling - Fanuc` . Fanuc is the dialect of the WinCNC control software on the router.
    - In Post settings → Fixed cycles, turn all options off
4. **Create a Setup**
    - Click `Create Setup`
    - General → Position Type = `Stock box point`
    - Scroll down to the Position panel
    - Select a point on your part that is on the face you will zero your tool on
    - Click `Ok`
5. **Create a Tool**
    - If you have a library of tools (future addition), choose the correct tool for your operation.
    - If you do not have a tool library, you will need to create a new tool for each tool you are using
6. **Create Toolpath**
    
    <aside>
    
    **Profiles**
    
    **Strategy**
    
    - Type = `Edges`
    - Pattern = `2-Axis Profile`
    
    **Drive Edges**
    
    - Select all edges for the toolpath to follow (Loop on)
    
    **Sorting**
    
    - Cutting Side = Right
    - Cutting Method = Spiral
    - **Heights**
    - End Height = Material Thickness (Negative Value!)
    
    **Speeds**
    
    - Reference [speeds/feeds table](https://www.notion.so/CNC-Router-Tooling-2a842da8b6c580ff91c6d65a669c7352?pvs=21)
    
    Chose the `Link` tab at the top and select `Global Lead In`
    
    - Type = Vertical profile ramp
    - Axis orientation = Tangential
    - Maximum angle change = 3
    - Length =6”
    - Height = same as layer height (0.05”)
    - Feed rate = 60%
    </aside>
    
    <aside>
    
    **Pockets**
    
    **Strategy**
    
    - Type = `Edges`
    - Pattern = `2-Axis Rough`
    
    **Drive Edges**
    
    - Selection Filter = **Loop**
    - Toggle Loop = `OFF`
    
    **Step Over**
    
    - Type = `Tool Diameter %`
    - Maximum Step Over = `25%`
    
    **Sorting**
    
    - Cutting Method = `Zigzag`
    - Cutting Direction = `Climb`
    - Machine By = `Regions`
    
    **Speeds**
    
    - Reference [speeds/feeds table](https://www.notion.so/CNC-Router-Tooling-2a842da8b6c580ff91c6d65a669c7352?pvs=21)
    </aside>
    
    <aside>
    
    **Holes**
    
    **Strategy**
    
    - Type = `Holes`
    - Pattern = `Drilling`
    
    **Holes**
    
    - Manually select holes you want to drill or select all with `Select all through holes`
    
    **Common**
    
    - Custom Depth = Material Thickness
    </aside>
    
    <aside>
    ⚠️
    
    Just because the feature you want to cut is a hole, doesn’t mean you should select hole. Holes are only for when you can drill the entire hole with a single drill bit plunge, otherwise select edges.
    
    </aside>
    
7. **Verify and Post**
   - Click the play button for each toolpath to preview each path individually, or click the play button under each setup to preview all toolpaths at the same time.
   - Check the box next to the toolpath you want to post, then click `Post selected operations` next to the setup for that toolpath.
   - Run the exported file through Onshape-to-WinCNC.pyw
